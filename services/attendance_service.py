from datetime import datetime, timedelta
import pandas as pd

TIME_FLAG = 1

def parse_timestamp(ts):
    try:
        return datetime.strptime(str(ts), "%Y%m%d%H%M%S")
    except:
        return None

def check_morning_shift_with_missing_log(fci, log_count):
    if log_count <= 1:
        if 5 <= fci.hour <= 10 or fci.hour < 22:
            return 'Ca sáng thiếu log'
    return None

def process_attendance(df):
    df = df.rename(columns={
        df.columns[0]: "timestamp",
        df.columns[1]: "unused",  # bỏ qua
        df.columns[2]: "id",
        df.columns[3]: "first_name",
        df.columns[4]: "last_name",
        df.columns[5]: "key"
    })

    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    df.dropna(subset=['datetime'], inplace=True)
    df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
    df = df.sort_values(by=['id', 'datetime'])

    records = []
    grouped = df.groupby(['id', 'full_name'])

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime').reset_index(drop=True)
        group['date'] = group['datetime'].dt.date  # thêm để tra log hôm trước

        i = 0
        while i < len(group):
            row = group.iloc[i]
            if row['key'] != 'Vào':
                i += 1
                continue

            fci = row['datetime']
            fci_status = row['key']
            shift_type = "Không hợp lệ"
            lco = fci
            lco_status = "Không có"
            log_count = 1
            found_lco = False

            j = i + 1
            while j < len(group):
                next_row = group.iloc[j]
                time_diff = (next_row['datetime'] - fci).total_seconds() / 3600

                if next_row['key'] == 'Ra' and time_diff <= 30:  # ca thông ca có thể dài
                    lco = next_row['datetime']
                    lco_status = next_row['key']
                    log_count += 1
                    found_lco = True
                    break
                j += 1

            duration = (lco - fci).total_seconds() / 3600
            date_report = fci.date()

            # Phân loại ca
            if log_count <= 1:
                morning_shift = check_morning_shift_with_missing_log(fci, log_count)
                shift_type = morning_shift if morning_shift else 'Thiếu log'
            else:
                if duration >= 22:
                    shift_type = 'Thông ca'
                elif 5 <= fci.hour <= 10 and lco.hour < 20 and duration >= TIME_FLAG:
                    shift_type = 'Ca sáng'
                elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                    if lco.date() > fci.date() or lco.hour <= 8:
                        shift_type = 'Ca đêm'

            # Tìm log hôm trước nếu thiếu log
            prev_day = date_report - timedelta(days=1)
            prev_log_info = "None"
            group_by_date = group.groupby('date')

            if shift_type in ['Thiếu log', 'Ca sáng thiếu log']:
                if prev_day in group_by_date.groups:
                    prev_logs = group_by_date.get_group(prev_day)
                    prev_entries = [
                        f"{r['key']} @ {r['datetime'].strftime('%H:%M:%S')}"
                        for _, r in prev_logs.iterrows()
                    ]
                    prev_log_info = "; ".join(prev_entries)

            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': date_report,
                'FCI': fci.strftime('%d/%m - %H:%M:%S'),
                'FCI trạng thái': fci_status,
                'LCO': lco.strftime('%d/%m - %H:%M:%S'),
                'LCO trạng thái': lco_status,
                'Thời lượng (h)': round(duration, 2),
                'Loại ca': shift_type,
                'Log hôm trước': prev_log_info
            })

            i = j if found_lco else i + 1

    return pd.DataFrame(records)