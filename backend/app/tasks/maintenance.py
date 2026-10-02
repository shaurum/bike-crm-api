import logging
import subprocess
import os
from celery import shared_task
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@shared_task
def daily_backup():
    import asyncio
    asyncio.run(_daily_backup())


async def _daily_backup():
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = "/app/backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = f"{backup_dir}/db_{timestamp}.sql.gz"

        cmd = [
            "pg_dump",
            "-h", settings.POSTGRES_SERVER,
            "-p", str(settings.POSTGRES_PORT),
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "--no-owner",
            "--no-privileges",
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        proc = subprocess.run(cmd, capture_output=True, env=env)
        if proc.returncode != 0:
            logger.error(f"pg_dump failed: {proc.stderr.decode()}")
            return

        import gzip
        with gzip.open(backup_file, "wb") as f:
            f.write(proc.stdout)

        logger.info(f"Backup created: {backup_file}")

        if settings.S3_ENDPOINT and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY:
            upload_to_s3(backup_file, f"backups/db_{timestamp}.sql.gz")

        cleanup_old_backups(backup_dir)

    except Exception as e:
        logger.exception(f"Backup error: {e}")


def upload_to_s3(local_path: str, s3_key: str):
    import boto3
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        s3.upload_file(local_path, settings.S3_BUCKET, s3_key)
        logger.info(f"Backup uploaded to S3: {s3_key}")
    except Exception as e:
        logger.exception(f"S3 upload error: {e}")


def cleanup_old_backups(backup_dir: str, keep_days: int = 30):
    try:
        now = datetime.now()
        for fname in os.listdir(backup_dir):
            fpath = os.path.join(backup_dir, fname)
            if os.path.isfile(fpath):
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if (now - mtime).days > keep_days:
                    os.remove(fpath)
                    logger.info(f"Removed old backup: {fname}")
    except Exception as e:
        logger.exception(f"Cleanup error: {e}")


@shared_task
def check_bike_battery():
    import asyncio
    asyncio.run(_check_bike_battery())


async def _check_bike_battery():
    async with async_session_maker() as session:
        from app.models import Bike, BikeStatus, Task, TaskType, User, UserRole
        result = await session.execute(
            select(Bike).where(Bike.status == BikeStatus.RENTED, Bike.battery_capacity.isnot(None))
        )
        bikes = result.scalars().all()

        mechanic = await session.execute(
            select(User).where(User.role == UserRole.MECHANIC, User.is_active == True).limit(1)
        )
        mechanic = mechanic.scalar_one_or_none()

        for bike in bikes:
            battery_pct = bike.specs.get("battery_percent", 100)
            if battery_pct < 20:
                existing = await session.execute(
                    select(Task).where(
                        Task.related_bike_id == bike.id,
                        Task.type == TaskType.MAINTENANCE,
                        Task.status.in_(["todo", "in_progress"]),
                    )
                )
                if not existing.scalar_one_or_none():
                    task = Task(
                        type=TaskType.MAINTENANCE,
                        title=f"Зарядка байка {bike.model}",
                        description=f"Уровень батареи: {battery_pct}%",
                        due_at=datetime.now(timezone.utc),
                        related_bike_id=bike.id,
                        assignee_id=mechanic.id if mechanic else None,
                    )
                    session.add(task)

        await session.commit()