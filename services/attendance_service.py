from datetime import datetime, timedelta
import pandas as pd
import re

TIME_FLAG = 1

def parse_timestamp(ts):
    try:
        return datetime.strptime(str(ts), "%Y%m%d%H%M%S")
    except:
        return None

def natural_sort_key(val):
    parts = re.split(r'(\d+)', str(val))
    return [int(part) if part.isdigit() else part.lower() for part in parts]

def format_duration(hours):
    if pd.isna(hours):
        return ""
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h} giờ {m} phút" if total_minutes > 0 else "0 phút"

def check_morning_shift_with_missing_log(fci, log_count):
    if log_count <= 1:
        if 5 <= fci.hour <= 10 or fci.hour < 22:
            return 'Ca sáng thiếu log'
    return None

def handle_single_logs(group, processed_indices, emp_id, name, records):
    for idx, row in group.iterrows():
        if idx in processed_indices:
            continue

        log_date = row['datetime'].date()
        if row['key'] == 'Vào':
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                'FCI trạng thái': 'Vào',
                'LCO': 'Không có',
                'LCO trạng thái': 'Không có',
                'Thời lượng (h)': 0,
                'Loại ca': 'Thiếu LCO',
                'Log hôm trước': 'None'
            })

        elif row['key'] == 'Ra':
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': log_date,
                'FCI': 'Không có',
                'FCI trạng thái': 'Không có',
                'LCO': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                'LCO trạng thái': 'Ra',
                'Thời lượng (h)': 0,
                'Loại ca': 'Thiếu FCI',
                'Log hôm trước': 'None'
            })

def process_attendance(df):
    df = df.rename(columns={
        df.columns[0]: "timestamp",
        df.columns[1]: "unused",
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
        group['date'] = group['datetime'].dt.date
        group_by_date = group.groupby('date')

        processed_indices = set()
        i = 0 

        # Bắt FCI hiện tại
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

            processed_indices.add(i)

            j = i + 1
            while j < len(group):
                next_row = group.iloc[j]
                time_diff = (next_row['datetime'] - fci).total_seconds() / 3600

                # Dựa trên FCI đầu tiên bắt được để xét các log tiếp theo
                # Nếu là log "Ra" và thời gian cách nhau <= 30 phút thì coi là LCO và tiến hành ghép

                # Nếu có từ 2 log "Vào" thì render ra cả 2
                if next_row['key'] == 'Ra' and time_diff <= 30:
                    lco = next_row['datetime']
                    lco_status = next_row['key']
                    log_count += 1
                    found_lco = True
                    processed_indices.add(j)
                    break
                j += 1

            duration = (lco - fci).total_seconds() / 3600
            date_report = fci.date()

            if log_count <= 1:
                morning_shift = check_morning_shift_with_missing_log(fci, log_count)
                shift_type = morning_shift if morning_shift else 'Thiếu log'
            else:
                if duration >= 17:
                    shift_type = 'Thông ca'
                elif 5 <= fci.hour <= 10 and lco.hour < 20 and duration >= TIME_FLAG:
                    shift_type = 'Ca sáng'
                elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                    if lco.date() > fci.date() or lco.hour <= 8:
                        shift_type = 'Ca đêm'

            prev_day = date_report - timedelta(days=1)
            prev_log_info = "Không có"

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

        # Ghi lại các log đơn lẻ chưa xử lý
        handle_single_logs(group, processed_indices, emp_id, name, records)

    df_result = pd.DataFrame(records)
    df_result['Ghi chú'] = ""  # Thêm cột ghi chú trống
    df_result.sort_values(by='ID', key=lambda x: x.map(natural_sort_key), inplace=True)

    return df_result