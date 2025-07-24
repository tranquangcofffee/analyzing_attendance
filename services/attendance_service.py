from datetime import datetime, timedelta
import pandas as pd

def parse_timestamp(ts):
    try:
        return datetime.strptime(str(ts), "%Y%m%d%H%M%S")
    except:
        return None

def process_attendance(df):
    df = df.rename(columns={df.columns[0]: "timestamp",
                            df.columns[2]: "id",
                            df.columns[3]: "first_name",
                            df.columns[4]: "last_name"})

    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    df.dropna(subset=['datetime'], inplace=True)
    df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
    df['date'] = df['datetime'].dt.date

    # Sắp xếp theo id, full_name và datetime
    df = df.sort_values(by=['id', 'full_name', 'datetime'])

    records = []
    # Nhóm theo id, full_name và date
    grouped = df.groupby(['id', 'full_name', 'date'])

    for (emp_id, name, date), group in grouped:
        group = group.sort_values(by='datetime')
        if len(group) == 0:
            continue

        # Lấy FCI sớm nhất và LCO muộn nhất trong ngày
        fci = group.iloc[0]['datetime']
        lco = group.iloc[-1]['datetime']
        duration = (lco - fci).total_seconds() / 3600
        shift_type = 'Không hợp lệ'

        # Phân loại ca
        if duration > 22:
            shift_type = 'Thông ca'
        elif 5 <= fci.hour <= 10 and lco.hour < 22 and duration >= 4:
            shift_type = 'Ca sáng'
        elif 16 <= fci.hour <= 19 and 4 <= duration < 14:
            if lco.date() > fci.date() or (lco.date() == fci.date() and lco.hour < 8):
                shift_type = 'Ca đêm'

        # Ghi lại record với định dạng ngày và giờ
        records.append({
            'ID': emp_id,
            'Họ tên': name,
            'Ngày': date,
            'FCI': fci.strftime('%Y-%m-%d %H:%M:%S'),
            'LCO': lco.strftime('%Y-%m-%d %H:%M:%S'),
            'Thời lượng (h)': round(duration, 2),
            'Loại ca': shift_type
        })

    return pd.DataFrame(records)