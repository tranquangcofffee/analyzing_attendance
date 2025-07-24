from datetime import datetime, timedelta
import pandas as pd

def parse_timestamp(ts):
    try:
        return datetime.strptime(str(ts), "%Y%m%d%H%M%S")
    except:
        return None

def check_morning_shift_with_missing_log(fci, log_count):
    """
    Kiểm tra nếu log duy nhất hoặc thiếu log thuộc ca sáng.
    - Nếu log_count <= 1 và FCI (hoặc LCO) trong 5:00-10:00 hoặc LCO trước 22:00, trả về 'Ca sáng thiếu log'.
    """
    if log_count <= 1:
        if 5 <= fci.hour <= 10 or fci.hour < 22:  # FCI trong 5:00-10:00 hoặc LCO trước 22:00
            return 'Ca sáng thiếu log'
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
    # Nhóm theo id và full_name để xử lý ca liên tục qua ngày
    grouped = df.groupby(['id', 'full_name'])

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime')
        i = 0
        while i < len(group):
            fci = group.iloc[i]['datetime']
            date = fci.date()
            lco = fci
            j = i + 1
            shift_type = 'Không hợp lệ'
            log_count = 1

            # Tìm LCO trong khoảng thời gian hợp lý (dưới 14 giờ)
            while j < len(group):
                next_time = group.iloc[j]['datetime']
                if (next_time - fci).total_seconds() / 3600 <= 14:
                    lco = next_time
                    log_count += 1
                    j += 1
                else:
                    break

            duration = (lco - fci).total_seconds() / 3600

            # Kiểm tra ca sáng thiếu log hoặc thiếu log thông thường
            if log_count <= 1:
                morning_shift = check_morning_shift_with_missing_log(fci, log_count)
                if morning_shift:
                    shift_type = morning_shift
                else:
                    shift_type = 'Thiếu log'
            else:
                # Phân loại ca
                if duration >= 22:
                    shift_type = 'Thông ca'
                elif 5 <= fci.hour <= 10 and lco.hour < 22 and duration >= 4:
                    shift_type = 'Ca sáng'
                elif 16 <= fci.hour <= 19 and duration >= 4 and log_count >= 2:
                    if lco.date() > fci.date() or lco.hour < 8 or duration >= 11:
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