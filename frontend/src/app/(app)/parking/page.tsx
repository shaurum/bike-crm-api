import { Bike } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function ParkingPage() {
  return (
    <PagePlaceholder
      title="Парковка"
      description="Флот электробайков: состояние, заряд батареи, обслуживание"
      icon={Bike}
      hint="Скоро здесь будет список байков"
    />
  );
}