import { api } from "./client";

export interface TimezoneItem {
  iana_name: string;
  label_zh: string;
  region: string;
  region_label_zh: string;
  utc_offset_label: string;
  display_label: string;
}

export const timezonesApi = {
  list: () => api.get<{ items: TimezoneItem[] }>("/timezones"),
};
