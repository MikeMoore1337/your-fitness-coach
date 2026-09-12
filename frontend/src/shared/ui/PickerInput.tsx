import type { ComponentPropsWithoutRef } from 'react';
import { Icon } from './Icon';

type PickerInputProps = Omit<ComponentPropsWithoutRef<'input'>, 'type'> & {
  controlClassName?: string;
};

export function DateInput({ controlClassName = '', ...props }: PickerInputProps) {
  return (
    <div className={`date-control ${controlClassName}`.trim()}>
      <input {...props} type="date" />
      <Icon className="date-control__icon" name="calendar" size={20} />
    </div>
  );
}

export function TimeInput({ controlClassName = '', ...props }: PickerInputProps) {
  return (
    <div className={`time-control ${controlClassName}`.trim()}>
      <input {...props} type="time" />
    </div>
  );
}
