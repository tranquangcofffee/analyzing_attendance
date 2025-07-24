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

    # Sắp xếp theo id và datetime để đảm bảo xử lý theo thứ tự thời gian
    df = df.sort_values(by=['id', 'datetime'])

    records = []
    # Nhóm theo id và full_name, không nhóm theo date để xử lý ca liên tục
    grouped = df.groupby(['id', 'full_name'])

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime')
        i = 0
        while i < len(group):
            fci = group.iloc[i]['datetime']
            date = fci.date()
            lco = fci
            j = i + 1

            # Tìm LCO trong khoảng thời gian hợp lý (dưới 16 giờ)
            while j < len(group):
                next_time = group.iloc[j]['datetime']
                if (next_time - fci).total_seconds() / 3600 <= 16:
                    lco = next_time
                    j += 1
                else:
                    break

            duration = (lco - fci).total_seconds() / 3600
            shift_type = 'Không hợp lệ'

            # Phân loại ca
            if duration >= 22:
                shift_type = 'Thông ca'
            elif 5 <= fci.hour <= 10 and lco.hour < 20 and duration >= 4:
                shift_type = 'Ca sáng'
            elif 16 <= fci.hour <= 19 and duration >= 4:
                if lco.date() > fci.date() or lco.hour < 8 and duration >= 11:
                    shift_type = 'Ca đêm'

            # Ghi lại record
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày': date,
                'FCI': fci.strftime('%H:%M:%S'),
                'LCO': lco.strftime('%H:%M:%S'),
                'Thời lượng (h)': round(duration, 2),
                'Loại ca': shift_type
            })

            i = j

    return pd.DataFrame(records)