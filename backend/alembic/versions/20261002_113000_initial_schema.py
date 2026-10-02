"""initial schema

Revision ID: 001
Revises: 
Create Date: 2026-10-02 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
import uuid

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


lead_source_type_enum = ENUM(
    'avito', 'vk', 'telegram', 'email', 'widget', 'manual',
    name='lead_source_type_enum',
    create_type=True
)

lead_status_enum = ENUM(
    'new', 'contacted', 'qualified', 'booking', 'won', 'lost',
    name='lead_status_enum',
    create_type=True
)

task_type_enum = ENUM(
    'call', 'meeting', 'contract', 'maintenance', 'handover', 'return', 'custom',
    name='task_type_enum',
    create_type=True
)

task_status_enum = ENUM(
    'todo', 'in_progress', 'done', 'cancelled',
    name='task_status_enum',
    create_type=True
)

bike_status_enum = ENUM(
    'available', 'reserved', 'rented', 'maintenance', 'charging', 'relocation',
    name='bike_status_enum',
    create_type=True
)

booking_status_enum = ENUM(
    'pending', 'confirmed', 'active', 'completed', 'cancelled', 'no_show',
    name='booking_status_enum',
    create_type=True
)

user_role_enum = ENUM(
    'admin', 'manager', 'mechanic',
    name='user_role_enum',
    create_type=True
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        'lead_source',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('type', lead_source_type_enum, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('config', JSONB, nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_lead_source_type_active', 'lead_source', ['type', 'is_active'])

    op.create_table(
        'pipeline_stage',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('color', sa.String(7), nullable=False, server_default='#3B82F6'),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('auto_actions', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_pipeline_stage_order', 'pipeline_stage', ['order'])

    op.create_table(
        'branch',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('address', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='Europe/Moscow'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'user',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('role', user_role_enum, nullable=False, server_default='manager'),
        sa.Column('branch_id', UUID(as_uuid=True), sa.ForeignKey('branch.id', ondelete='SET NULL'), nullable=True),
        sa.Column('telegram_chat_id', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_user_email', 'user', ['email'])
    op.create_index('ix_user_branch_role', 'user', ['branch_id', 'role'])

    op.create_table(
        'lead',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('source_id', UUID(as_uuid=True), sa.ForeignKey('lead_source.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=False),
        sa.Column('raw_payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('client_name', sa.String(255), nullable=True),
        sa.Column('client_phone', sa.String(50), nullable=True),
        sa.Column('client_email', sa.String(255), nullable=True),
        sa.Column('status', lead_status_enum, nullable=False, server_default='new'),
        sa.Column('stage_id', UUID(as_uuid=True), sa.ForeignKey('pipeline_stage.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_to_id', UUID(as_uuid=True), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('utm', JSONB, nullable=False, server_default='{}'),
        sa.Column('initial_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_lead_source_external_id', 'lead', ['source_id', 'external_id'], unique=True)
    op.create_index('ix_lead_status_stage', 'lead', ['status', 'stage_id'])
    op.create_index('ix_lead_assigned_to', 'lead', ['assigned_to_id'])
    op.create_index('ix_lead_phone', 'lead', ['client_phone'])
    op.create_index('ix_lead_created_at', 'lead', ['created_at'])

    op.create_table(
        'lead_message',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('lead_id', UUID(as_uuid=True), sa.ForeignKey('lead.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('external_msg_id', sa.String(255), nullable=True),
        sa.Column('meta', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_lead_message_lead_created', 'lead_message', ['lead_id', 'created_at'])
    op.create_index('ix_lead_message_external', 'lead_message', ['external_msg_id'])

    op.create_table(
        'task',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('type', task_type_enum, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', task_status_enum, nullable=False, server_default='todo'),
        sa.Column('related_lead_id', UUID(as_uuid=True), sa.ForeignKey('lead.id', ondelete='SET NULL'), nullable=True),
        sa.Column('related_booking_id', UUID(as_uuid=True), sa.ForeignKey('booking.id', ondelete='SET NULL'), nullable=True),
        sa.Column('related_bike_id', UUID(as_uuid=True), sa.ForeignKey('bike.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assignee_id', UUID(as_uuid=True), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_task_status_due', 'task', ['status', 'due_at'])
    op.create_index('ix_task_assignee', 'task', ['assignee_id'])
    op.create_index('ix_task_related_lead', 'task', ['related_lead_id'])
    op.create_index('ix_task_related_booking', 'task', ['related_booking_id'])
    op.create_index('ix_task_related_bike', 'task', ['related_bike_id'])

    op.create_table(
        'booking_widget',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('domain', sa.String(255), nullable=False, unique=True),
        sa.Column('config', JSONB, nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_booking_widget_domain_active', 'booking_widget', ['domain', 'is_active'])

    op.create_table(
        'contract_template',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('html_template', sa.Text, nullable=False),
        sa.Column('variables', JSONB, nullable=False, server_default='{}'),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'bike',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('branch_id', UUID(as_uuid=True), sa.ForeignKey('branch.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('frame_number', sa.String(100), nullable=True, unique=True),
        sa.Column('color', sa.String(50), nullable=True),
        sa.Column('year', sa.Integer, nullable=True),
        sa.Column('battery_capacity', sa.Float, nullable=True),
        sa.Column('max_speed', sa.Integer, nullable=True),
        sa.Column('range_km', sa.Integer, nullable=True),
        sa.Column('purchase_price', sa.Float, nullable=True),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', bike_status_enum, nullable=False, server_default='available'),
        sa.Column('current_location', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('specs', JSONB, nullable=False, server_default='{}'),
        sa.Column('photos', JSONB, nullable=False, server_default='[]'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_bike_branch_status', 'bike', ['branch_id', 'status'])
    op.create_index('ix_bike_frame_number', 'bike', ['frame_number'])
    op.create_index('ix_bike_status', 'bike', ['status'])

    op.create_table(
        'bike_price',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('bike_id', UUID(as_uuid=True), sa.ForeignKey('bike.id', ondelete='CASCADE'), nullable=False),
        sa.Column('duration_min', sa.Integer, nullable=False),
        sa.Column('duration_max', sa.Integer, nullable=True),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('deposit', sa.Float, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_bike_price_bike_active', 'bike_price', ['bike_id', 'is_active'])

    op.create_table(
        'customer',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('passport_series', sa.String(10), nullable=True),
        sa.Column('passport_number', sa.String(20), nullable=True),
        sa.Column('passport_issued_by', sa.String(255), nullable=True),
        sa.Column('passport_issued_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('address', sa.Text, nullable=True),
        sa.Column('driver_license', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('is_blacklisted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_customer_phone', 'customer', ['phone'])
    op.create_index('ix_customer_email', 'customer', ['email'])
    op.create_index('ix_customer_passport', 'customer', ['passport_series', 'passport_number'])

    op.create_table(
        'booking',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('branch_id', UUID(as_uuid=True), sa.ForeignKey('branch.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('bike_id', UUID(as_uuid=True), sa.ForeignKey('bike.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('customer_id', UUID(as_uuid=True), sa.ForeignKey('customer.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('lead_id', UUID(as_uuid=True), sa.ForeignKey('lead.id', ondelete='SET NULL'), nullable=True),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actual_start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', booking_status_enum, nullable=False, server_default='pending'),
        sa.Column('price_per_period', sa.Float, nullable=False),
        sa.Column('deposit_amount', sa.Float, nullable=False, server_default='0'),
        sa.Column('total_price', sa.Float, nullable=False),
        sa.Column('paid_amount', sa.Float, nullable=False, server_default='0'),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('handover_notes', sa.Text, nullable=True),
        sa.Column('return_notes', sa.Text, nullable=True),
        sa.Column('damage_report', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_booking_bike_dates', 'booking', ['bike_id', 'start_at', 'end_at'])
    op.create_index('ix_booking_customer', 'booking', ['customer_id'])
    op.create_index('ix_booking_status_dates', 'booking', ['status', 'start_at', 'end_at'])
    op.create_index('ix_booking_branch_dates', 'booking', ['branch_id', 'start_at', 'end_at'])
    op.create_index('ix_booking_lead', 'booking', ['lead_id'])

    op.create_table(
        'maintenance_record',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('bike_id', UUID(as_uuid=True), sa.ForeignKey('bike.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('cost', sa.Float, nullable=False, server_default='0'),
        sa.Column('performed_by', sa.String(100), nullable=True),
        sa.Column('next_maintenance_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mileage', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_maintenance_bike_date', 'maintenance_record', ['bike_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('maintenance_record')
    op.drop_table('booking')
    op.drop_table('customer')
    op.drop_table('bike_price')
    op.drop_table('bike')
    op.drop_table('contract_template')
    op.drop_table('booking_widget')
    op.drop_table('task')
    op.drop_table('lead_message')
    op.drop_table('lead')
    op.drop_table('user')
    op.drop_table('branch')
    op.drop_table('pipeline_stage')
    op.drop_table('lead_source')

    lead_source_type_enum.drop(op.get_bind(), checkfirst=True)
    lead_status_enum.drop(op.get_bind(), checkfirst=True)
    task_type_enum.drop(op.get_bind(), checkfirst=True)
    task_status_enum.drop(op.get_bind(), checkfirst=True)
    bike_status_enum.drop(op.get_bind(), checkfirst=True)
    booking_status_enum.drop(op.get_bind(), checkfirst=True)
    user_role_enum.drop(op.get_bind(), checkfirst=True)