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

    grouped = df.groupby(['id', 'full_name', 'date'])
    records = []

    for (emp_id, name, date), group in grouped:
        fci = group['datetime'].min()
        lco = group['datetime'].max()

        shift_type = 'Không hợp lệ'
        duration = (lco - fci).total_seconds() / 3600

        if duration >= 23:
            shift_type = 'Thông ca'
        elif 5 <= fci.hour <= 10 and lco.hour < 20:
            shift_type = 'Ca sáng'
        elif 16 <= fci.hour <= 19:
            if lco < fci + timedelta(hours=16):  # lco trước 8h sáng hôm sau
                shift_type = 'Ca đêm'

        records.append({
            'ID': emp_id,
            'Họ tên': name,
            'Ngày': date,
            'FCI': fci.strftime('%H:%M:%S'),
            'LCO': lco.strftime('%H:%M:%S'),
            'Thời lượng (h)': round(duration, 2),
            'Loại ca': shift_type
        })

    return pd.DataFrame(records)
