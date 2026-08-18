import { cn } from "@/lib/utils";

interface SyntheticEditorialDisclosureProps {
  className?: string;
  id?: string;
}

export function SyntheticEditorialDisclosure({
  className,
  id,
}: SyntheticEditorialDisclosureProps) {
  return (
    <p id={id} className={cn("text-xs font-medium leading-5", className)}>
      AI-generated editorial illustration. The people and workplace shown are
      not Praviar staff, customers, facilities, or a case study.
    </p>
  );
}
