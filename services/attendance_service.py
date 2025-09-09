from datetime import datetime, timedelta
import pandas as pd
import re
from math import floor
from helpers.attendance_helpers import extract_time_only, parse_timestamp, natural_sort_key, format_duration, handle_single_logs, replace_key_values, remove_nan_rows
from message_constant.message_constant import *

def handle_single_logs(group, processed_indices, emp_id, name, records):

    for idx, row in group.iterrows():
        if idx in processed_indices:
            continue

        log_date = row['datetime'].strftime('%d/%m/%Y')
        fci = row['datetime']
        
        # Kiểm tra ca sáng thiếu log
        log_count = 1  # Giả sử chỉ có 1 log (Vào hoặc Ra)
        shift_type = None
        if row['key'] == 'Vào':
            if 5 <= fci.hour <= 10 or fci.hour < 22:
                shift_type = 'Ca sáng thiếu log'
            else:
                shift_type = 'Thiếu giờ ra'
                
            records.append({
                'ID': emp_id,
                'Họ tên': name,
                'Ngày chấm công': log_date,
                'Giờ vào': 'Không có',
                'Giờ ra': 'Không có',
                'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                'FCI (giờ)': 'Không có',
                'LastCheckOut': 'Không có',
                'LCO (giờ)': 'Không có',
                'Thời lượng (h)': 0,
                'Thời lượng': 0,
                'Loại ca': shift_type
            })

        elif row['key'] == 'Ra':  
            # Tìm xem có FCI trước đó không
            previous_fci = group[(group['datetime'] < row['datetime']) & (group['key'] == 'Vào')]
            
            if not previous_fci.empty:
                # Có FCI trước đó => log này là LCO hợp lệ, bỏ qua ở đây
                continue
            else:
                # Không có FCI trước đó => check thêm khung giờ
                if 0 <= row['datetime'].hour <= 8:
                    # Có thể là LCO của ca đêm hôm trước => KHÔNG coi là thiếu FCI
                    continue
                else:
                    # Thực sự là thiếu FCI
                    shift_type = 'Thiếu giờ vào'
                    records.append({
                        'ID': emp_id,
                        'Họ tên': name,
                        'Ngày chấm công': log_date,
                        'Giờ vào': 'Không có',
                        'Giờ ra': 'Không có',
                        'FirstCheckIn': 'Không có',
                        'FCI (giờ)': 'Không có',
                        'LastCheckOut': row['datetime'].strftime('%d/%m - %H:%M:%S'),
                        'LCO (giờ)': 'Không có',
                        'Thời lượng (h)': 0,
                        'Thời lượng': 0,
                        'Loại ca': shift_type
                    })


# df_result = df_result[[
#         'ID', 'Họ tên', 'Ngày chấm công',
#         'Giờ vào', 'Giờ ra',
#         'FirstCheckIn', 'FCI (giờ)',
#         'LastCheckOut', 'LCO (giờ)',
#         'Thời lượng (h)', 'Thời lượng', 'Loại ca',
#         'Ghi chú'
#     ]]

def handle_machine_failure(df_result):
    """Xử lý sự cố máy quét từ 6h ngày 2/9/2025 đến 9h10 ngày 4/9/2025, bù 31 tiếng."""
    failure_start = datetime(2025, 9, 2, 6, 0, 0)
    failure_end = datetime(2025, 9, 4, 9, 10, 0)
    compensation_hours = 31.0
    specific_check_time = datetime(2025, 9, 3, 1, 19, 51)  # Bản ghi cụ thể của bạn

    compensated_count = 0
    debug_logs = []

    for idx, row in df_result.iterrows():
        try:
            fci_str = row['FirstCheckIn']
            lco_str = row['LastCheckOut']
            
            # Parse FCI và LCO
            fci = pd.to_datetime(fci_str, format='%d/%m - %H:%M:%S', errors='coerce') if fci_str != 'Không có' else None
            lco = pd.to_datetime(lco_str, format='%d/%m - %H:%M:%S', errors='coerce') if lco_str != 'Không có' else None
            
            # Ghi log giá trị đã parse
            debug_logs.append(f"Bản ghi {idx}: FCI_str={fci_str}, LCO_str={lco_str}, FCI={fci}, LCO={lco}")

            # Kiểm tra nếu bản ghi nằm trong khoảng thời gian sự cố
            is_within_failure = False
            if fci is not None and (failure_start <= fci <= failure_end):
                is_within_failure = True
                debug_logs.append(f"Bản ghi {idx}: FCI {fci_str} nằm trong khoảng sự cố")
            elif lco is not None and (failure_start <= lco <= failure_end):
                is_within_failure = True
                debug_logs.append(f"Bản ghi {idx}: LCO {lco_str} nằm trong khoảng sự cố")
            elif fci is not None and lco is not None and (fci <= failure_end and lco >= failure_start):
                is_within_failure = True
                debug_logs.append(f"Bản ghi {idx}: FCI {fci_str} và LCO {lco_str} giao với khoảng sự cố")
            elif fci is not None and fci == specific_check_time:
                is_within_failure = True
                debug_logs.append(f"Bản ghi {idx}: FCI khớp chính xác 03/09 - 01:19:51")
            elif fci is not None and fci.date() in [datetime(2025, 9, 2).date(), datetime(2025, 9, 3).date()]:
                is_within_failure = True
                debug_logs.append(f"Bản ghi {idx}: FCI {fci_str} thuộc ngày 2/9 hoặc 3/9/2025")

            if is_within_failure:
                df_result.at[idx, 'Thời lượng (h)'] = compensation_hours
                df_result.at[idx, 'Thời lượng'] = format_duration(compensation_hours)
                df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + f" ({MACHINE_FAILURE_NOTE})"
                compensated_count += 1
                debug_logs.append(f"Bản ghi {idx}: Đã bù 31 tiếng")
            else:
                debug_logs.append(f"Bản ghi {idx}: Không nằm trong khoảng sự cố (FCI: {fci_str}, LCO: {lco_str})")
        except Exception as e:
            debug_logs.append(f"Bản ghi {idx}: Lỗi xử lý - {str(e)}")
            df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + f" (Lỗi xử lý sự cố máy quét: {str(e)})"
            continue

    # In log để debug
    print(f"Đã bù 31 tiếng cho {compensated_count} bản ghi trong khoảng thời gian sự cố.")
    for log in debug_logs:
        print(log)

    return df_result

def remove_nan_rows(df_result):
    """Loại bỏ các dòng có giá trị NaN trong các cột quan trọng."""
    important_columns = ['Thời lượng (h)', 'Giờ vào', 'Giờ ra', 'FirstCheckIn', 'LastCheckOut']
    initial_rows = len(df_result)
    df_result = df_result.dropna(subset=important_columns, how='any')
    removed_rows = initial_rows - len(df_result)
    if removed_rows > 0:
        print(f"Đã loại bỏ {removed_rows} dòng chứa NaN trong các cột: {important_columns}")
    return df_result

def apply_policy_adjustments(df_result, policy_df):
    """Áp dụng điều chỉnh chính sách từ file chính sách, lưu Giờ vào/ra theo chính sách, tính đi trễ/về sớm."""
    # Đảm bảo tên cột đúng
    expected_columns = ['ID', 'start_day', 'start_night', 'end_day', 'end_night', 'late_tol', 'early_tol', 'working_place']

    if not all(col in policy_df.columns for col in expected_columns):
        policy_df.columns = expected_columns[:len(policy_df.columns)]
    
    # Chuyển ID thành chuỗi và loại bỏ trùng lặp
    policy_df['ID'] = policy_df['ID'].astype(str)
    df_result['ID'] = df_result['ID'].astype(str)
    policy_df = policy_df.drop_duplicates(subset='ID')
    policy_map = policy_df.set_index('ID').to_dict('index')

    # Khởi tạo từ điển để lưu tổng thời gian đi trễ và về sớm theo ID
    late_early_summary = {}

    def parse_shift_time(date_ref, time_str):
        """Chuyển đổi chuỗi thời gian và kết hợp với ngày tham chiếu."""
        if pd.isna(time_str) or not isinstance(time_str, str) or time_str.strip() == '':
            return None
        try:
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
            return datetime.combine(date_ref.date(), time_obj)
        except ValueError:
            try:
                time_obj = datetime.strptime(time_str, "%H:%M").time()
                return datetime.combine(date_ref.date(), time_obj)
            except:
                return None

    # Thêm cột mới cho đi trễ/về sớm
    df_result['Đi trễ/Về sớm'] = ""

    # Thêm cột nơi làm việc 
    df_result['Nơi làm việc'] = ""

    for idx, row in df_result.iterrows():
        emp_id = str(row['ID'])
        if emp_id not in late_early_summary:
            late_early_summary[emp_id] = {'total_late': 0, 'total_early': 0}

        if emp_id not in policy_map:
            df_result.at[idx, 'Ghi chú'] = "Không tìm thấy chính sách cho ID {}".format(emp_id)
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Không có chính sách"
            df_result.at[idx, 'Nơi làm việc'] = "Không có chính sách"
            continue

        policy = policy_map[emp_id]
        shift_type = row.get('Loại ca', '')
        date_ref = row.get('Ngày chấm công')

        # Gán nơi làm việc vào 
        df_result.at[idx, 'Nơi làm việc'] = policy.get('working_place', '')

        # Kiểm tra và chuyển đổi date_ref
        try:
            if isinstance(date_ref, (datetime, pd.Timestamp)):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, str):
                date_ref = pd.Timestamp(date_ref)
            elif isinstance(date_ref, pd.Timestamp.date):
                date_ref = pd.Timestamp(date_ref)
            else:
                df_result.at[idx, 'Ghi chú'] = "Lỗi định dạng ngày"
                df_result.at[idx, 'Đi trễ/Về sớm'] = "Lỗi định dạng ngày"
                continue
        except Exception as e:
            df_result.at[idx, 'Ghi chú'] = "Thiếu dữ liệu chấm công"
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Lỗi định dạng ngày"
            continue

        # Bỏ qua nếu là Thông ca
        if 'Thông ca' in shift_type:
            df_result.at[idx, 'Ghi chú'] = "Thông ca được bỏ qua"
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Thông ca"
            continue

        # Xác định thời gian bắt đầu và kết thúc dựa trên loại ca
        if 'Ca đêm' in shift_type:
            shift_start = parse_shift_time(date_ref, policy.get('start_night'))
            shift_end = parse_shift_time(date_ref, policy.get('end_night'))
            if shift_end and shift_start and shift_end < shift_start:
                shift_end += timedelta(days=1)
        elif 'Ca sáng' in shift_type or 'Ca sáng thiếu log' in shift_type:
            shift_start = parse_shift_time(date_ref, policy.get('start_day'))
            shift_end = parse_shift_time(date_ref, policy.get('end_day'))
        else:
            df_result.at[idx, 'Ghi chú'] = f"Loại ca không được nhận diện: {shift_type}"
            df_result.at[idx, 'Đi trễ/Về sớm'] = "Loại ca không xác định"
            continue

        if not shift_start or not shift_end:
            df_result.at[idx, 'Ghi chú'] = " "
            df_result.at[idx, 'Đi trễ/Về sớm'] = " "
            continue

        # Gán Giờ vào và Giờ ra theo chính sách
        df_result.at[idx, 'Giờ vào'] = shift_start.strftime('%d/%m - %H:%M:%S') if shift_start else "Không có"
        df_result.at[idx, 'Giờ ra'] = shift_end.strftime('%d/%m - %H:%M:%S') if shift_end else "Không có"

        # Tính duration_2 từ chính sách
        duration_2 = (shift_end - shift_start).total_seconds() / 3600 if shift_start and shift_end else 0

        # Lấy duration_1 từ LastCheckOut - FirstCheckIn (nếu có)
        fci_str = row.get('FirstCheckIn')
        lco_str = row.get('LastCheckOut')
        duration_1 = row.get('Thời lượng (h)', 0)
        if fci_str != 'Không có' and lco_str != 'Không có':
            try:
                fci = pd.to_datetime(fci_str, format='%d/%m - %H:%M:%S')
                lco = pd.to_datetime(lco_str, format='%d/%m - %H:%M:%S')
                duration_1 = (lco - fci).total_seconds() / 3600
            except Exception as e:
                duration_1 = 0
                df_result.at[idx, 'Ghi chú'] = f"Lỗi parse FirstCheckIn/LastCheckOut: {str(e)}"
        else:
            fci = None
            lco = None
            df_result.at[idx, 'Ghi chú'] = "Thiếu check-in/check-out, dùng thời gian chính sách"

        # Tính đi trễ và về sớm với dung sai
        late_minutes = 0
        early_minutes = 0
        late_tolerance = float(policy.get('late_tol', 0)) if not pd.isna(policy.get('late_tol')) else 0
        early_tolerance = float(policy.get('early_tol', 0)) if not pd.isna(policy.get('early_tol')) else 0
        status = []

        if fci_str != 'Không có' and lco_str != 'Không có':
            # Đảm bảo fci và lco cùng ngày với shift_start và shift_end
            if fci.date() != shift_start.date():
                fci = datetime.combine(shift_start.date(), fci.time())
            if lco.date() != shift_end.date():
                lco = datetime.combine(shift_end.date(), lco.time())

            # Tính đi trễ với dung sai
            shift_start_with_tol = shift_start + timedelta(minutes=late_tolerance)
            if fci > shift_start_with_tol:
                late_minutes = floor((fci - shift_start_with_tol).total_seconds() / 60)
                if late_minutes > 0:
                    status.append(f"Đi trễ {int(late_minutes)} phút")
                    late_early_summary[emp_id]['total_late'] += late_minutes

            # Tính về sớm với dung sai
            shift_end_with_tol = shift_end - timedelta(minutes=early_tolerance)
            if lco < shift_end_with_tol:
                early_minutes = floor((shift_end_with_tol - lco).total_seconds() / 60)
                if early_minutes > 0 and early_minutes < 1440:
                    status.append(f"Về sớm {int(early_minutes)} phút")
                    late_early_summary[emp_id]['total_early'] += early_minutes

        # Logic đặc biệt cho ID 6 và 37
        if emp_id in ['6', '37']:
            total_late_early = late_minutes + early_minutes
            if total_late_early <= 60:
                status = []
                df_result.at[idx, 'Đi trễ/Về sớm'] = "Đúng giờ"
                df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + " (Tổng đi trễ/về sớm <= 60 phút, xét đúng giờ)"
                late_early_summary[emp_id]['total_late'] -= late_minutes
                late_early_summary[emp_id]['total_early'] -= early_minutes
            else:
                # Trừ 60 phút và phân bổ theo tỷ lệ
                excess_minutes = total_late_early - 60
                late_ratio = late_minutes / total_late_early if total_late_early > 0 else 0
                early_ratio = early_minutes / total_late_early if total_late_early > 0 else 0
                adjusted_late = floor(excess_minutes * late_ratio)
                adjusted_early = floor(excess_minutes * early_ratio)

                # Cập nhật lại summary
                late_early_summary[emp_id]['total_late'] -= late_minutes
                late_early_summary[emp_id]['total_early'] -= early_minutes
                late_early_summary[emp_id]['total_late'] += adjusted_late
                late_early_summary[emp_id]['total_early'] += adjusted_early

                # Cập nhật trạng thái
                status = []
                if adjusted_late > 0:
                    status.append(f"Đi trễ {int(adjusted_late)} phút")
                if adjusted_early > 0:
                    status.append(f"Về sớm {int(adjusted_early)} phút")
                df_result.at[idx, 'Đi trễ/Về sớm'] = ", ".join(status) if status else "Đúng giờ"
                df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + f" (Tổng đi trễ/về sớm {int(total_late_early)} phút, trừ 60 phút, còn {int(excess_minutes)} phút)"
        else:
            df_result.at[idx, 'Đi trễ/Về sớm'] = ", ".join(status) if status else "Đúng giờ"

        # Chọn thời lượng hợp lý
        if emp_id in ['6', '37'] and (late_minutes + early_minutes) <= 60:
            final_duration = duration_2
            df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + " (Dùng thời lượng chính sách vì tổng đi trễ/về sớm <= 60 phút)"
        elif duration_1 > duration_2:
            final_duration = duration_2
            df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + " (Dùng thời lượng chính sách (Giờ ra - Giờ vào))"
        else:
            final_duration = duration_1
            df_result.at[idx, 'Ghi chú'] = (df_result.at[idx, 'Ghi chú'] or "") + " (Dùng thời lượng thực tế (LastCheckOut - FirstCheckIn))"
            

        df_result.at[idx, 'Thời lượng (h)'] = round(final_duration, 2)
        df_result.at[idx, 'Thời lượng'] = format_duration(final_duration)

    # Tạo DataFrame tổng hợp đi trễ/về sớm
    summary_data = []
    for emp_id, summary in late_early_summary.items():
        summary_data.append({
            'ID': emp_id,
            'Tổng đi trễ (phút)': floor(summary['total_late']),
            'Tổng về sớm (phút)': floor(summary['total_early'])
        })
    summary_df = pd.DataFrame(summary_data)

    return df_result, summary_df

def process_attendance(df, policy_df=None):
    """Xử lý dữ liệu chấm công và áp dụng điều chỉnh chính sách."""

    # Nếu truyền vào là list thì convert sang DataFrame
    if isinstance(df, list):
        df = pd.DataFrame(df)
    elif not isinstance(df, pd.DataFrame):
        raise ValueError("process_attendance chỉ nhận DataFrame hoặc list of dict")
    
    # Đổi tên cột cho phù hợp
    df = df.rename(columns={
        df.columns[0]: "timestamp",
        df.columns[1]: "unused",
        df.columns[2]: "id",
        df.columns[3]: "first_name",
        df.columns[4]: "last_name",
        df.columns[5]: "key"
    })

    # Thay thế giá trị key (IN, IN DUTY -> Vào; OUT, OUT DUTY -> Ra)
    df = replace_key_values(df)

    # Phân tích timestamp và loại bỏ hàng không hợp lệ
    df['datetime'] = df['timestamp'].apply(parse_timestamp)
    df.dropna(subset=['datetime'], inplace=True)
    
    # Tạo tên đầy đủ và sắp xếp theo ID, thời gian
    df['full_name'] = df['first_name'].astype(str) + ' ' + df['last_name'].astype(str)
    df = df.sort_values(by=['id', 'datetime'])

    records = []
    grouped = df.groupby(['id', 'full_name'])

    for (emp_id, name), group in grouped:
        group = group.sort_values(by='datetime').reset_index()
        group['date'] = group['datetime'].dt.date
        group_by_date = group.groupby('date')

        processed_indices = set()
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

            processed_indices.add(i)

            j = i + 1
            while j < len(group):
                next_row = group.iloc[j]
                time_diff = (next_row['datetime'] - fci).total_seconds() / 3600

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
                shift_type = 'Thiếu log'
            else:
                if 17 <= fci.hour and duration >= 17:
                    # Dòng 1: Giữ nguyên bản ghi với shift_type = 'Thông ca'
                    record = {
                        'ID': str(emp_id),
                        'Họ tên': name,
                        'Ngày chấm công': date_report.strftime('%d/%m/%Y'),
                        'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                        'LastCheckOut': lco.strftime('%d/%m - %H:%M:%S'),
                        'Giờ vào': fci.strftime('%d/%m - %H:%M:%S'),
                        'Giờ ra': lco.strftime('%d/%m - %H:%M:%S'),
                        'Thời lượng (h)': round(duration, 2),
                        'Thời lượng': format_duration(duration),
                        'Loại ca': 'Thông ca',
                        'Log hôm trước': "Không có"
                    }
                    records.append(record)

                    # Ngày kế tiếp
                    next_day = fci + timedelta(days=1)

                    # Dòng 2: Từ fci đến 06:59:00 ngày kế tiếp (Ca đêm)
                    night_end = next_day.replace(hour=6, minute=59, second=0, microsecond=0)
                    if fci < night_end:
                        night_duration = (night_end - fci).total_seconds() / 3600
                        night_record = {
                            'ID': str(emp_id),
                            'Họ tên': name,
                            'Ngày chấm công': date_report.strftime('%d/%m/%Y'),
                            'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                            'LastCheckOut': night_end.strftime('%d/%m - %H:%M:%S'),
                            'Giờ vào': fci.strftime('%d/%m - %H:%M:%S'),
                            'Giờ ra': night_end.strftime('%d/%m - %H:%M:%S'),
                            'Thời lượng (h)': round(night_duration, 2),
                            'Thời lượng': format_duration(night_duration),
                            'Loại ca': 'Ca đêm',
                            'Log hôm trước': "Không có"
                        }
                        records.append(night_record)

                    # Dòng 3: Từ 07:00:00 ngày kế tiếp đến lco (Ca ngày)
                    day_start = next_day.replace(hour=7, minute=0, second=0, microsecond=0)
                    if day_start < lco:
                        day_duration = (lco - day_start).total_seconds() / 3600
                        if day_duration > 0:  # Đảm bảo thời lượng dương
                            day_record = {
                                'ID': str(emp_id),
                                'Họ tên': name,
                                'Ngày chấm công': day_start.strftime('%d/%m/%Y'),  # Cập nhật ngày theo day_start
                                'FirstCheckIn': day_start.strftime('%d/%m - %H:%M:%S'),
                                'LastCheckOut': lco.strftime('%d/%m - %H:%M:%S'),
                                'Giờ vào': day_start.strftime('%d/%m - %H:%M:%S'),
                                'Giờ ra': lco.strftime('%d/%m - %H:%M:%S'),
                                'Thời lượng (h)': round(day_duration, 2),
                                'Thời lượng': format_duration(day_duration),
                                'Loại ca': 'Ca sáng',
                                'Log hôm trước': "Không có"
                            }
                            records.append(day_record)

                elif 4 <= fci.hour <= 14 and lco.hour < 22 and duration >= TIME_FLAG:
                    same_day_logs = group[group['date'] == fci.date()]
                    morning_fc_in = same_day_logs[same_day_logs['key'] == 'Vào']
                    morning_lc_out = same_day_logs[same_day_logs['key'] == 'Ra']
                    
                    if len(morning_fc_in) > 1 or len(morning_lc_out) > 1:
                        earliest_fci = morning_fc_in['datetime'].min()
                        latest_lco = morning_lc_out[morning_lc_out['datetime'].dt.hour < 22]['datetime'].max()
                        new_duration = (latest_lco - earliest_fci).total_seconds() / 3600 if pd.notna(latest_lco) else 0
                        
                        if new_duration >= TIME_FLAG:
                            fci = earliest_fci
                            lco = latest_lco
                            duration = new_duration
                            shift_type = 'Ca sáng'
                        else:
                            shift_type = 'Ca sáng'
                    else:
                        shift_type = 'Ca sáng'
                    
                    record = {
                        'ID': str(emp_id),
                        'Họ tên': name,
                        'Ngày chấm công': date_report.strftime('%d/%m/%Y'),
                        'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                        'LastCheckOut': lco.strftime('%d/%m - %H:%M:%S'),
                        'Giờ vào': fci.strftime('%d/%m - %H:%M:%S'),
                        'Giờ ra': lco.strftime('%d/%m - %H:%M:%S'),
                        'Thời lượng (h)': round(duration, 2),
                        'Thời lượng': format_duration(duration),
                        'Loại ca': shift_type,
                        'Log hôm trước': "Không có"
                    }
                    records.append(record)

                elif 4 <= fci.hour <= 14 and lco.hour < 23 and duration >= TIME_FLAG:
                    same_day_logs = group[group['date'] == fci.date()]
                    morning_fc_in = same_day_logs[same_day_logs['key'] == 'Vào'] 
                    morning_lc_out = same_day_logs[same_day_logs['key'] == 'Ra']
                    
                    if len(morning_fc_in) > 1 or len(morning_lc_out) > 1:
                        earliest_fci = morning_fc_in['datetime'].min()
                        latest_lco = morning_lc_out[morning_lc_out['datetime'].dt.hour < 23]['datetime'].max()
                        new_duration = (latest_lco - earliest_fci).total_seconds() / 3600 if pd.notna(latest_lco) else 0
                        
                        if new_duration >= TIME_FLAG:
                            fci = earliest_fci
                            lco = latest_lco
                            duration = new_duration
                            shift_type = 'Ca sáng'
                    else:
                        shift_type = 'Ca sáng'
                        
                elif 4 <= fci.hour <= 14 and lco.hour > 22:
                    shift_type = 'Ca sáng tăng ca'

                elif 16 <= fci.hour <= 23 and duration >= TIME_FLAG:
                    if lco.date() > fci.date() or lco.hour <= 10:
                        shift_type = 'Ca đêm'
                    elif lco.hour > 10:
                        shift_type = 'Ca đêm tăng ca'

            prev_day = date_report - timedelta(days=1)
            prev_log_info = "Không có"

            if shift_type in ['Thiếu log', 'Ca sáng thiếu log', 'Thiếu FCI']:
                if prev_day in group_by_date.groups:
                    prev_logs = group_by_date.get_group(prev_day)
                    prev_entries = [
                        f"{r['key']} @ {r['datetime'].strftime('%H:%M:%S')}"
                        for _, r in prev_logs.iterrows()
                    ]
                    prev_log_info = "; ".join(prev_entries)

            records.append({
                'ID': str(emp_id),
                'Họ tên': name,
                'Ngày chấm công': date_report.strftime('%d/%m/%Y'),
                'FirstCheckIn': fci.strftime('%d/%m - %H:%M:%S'),
                #'FCIStatus': fci_status,
                'LastCheckOut': lco.strftime('%d/%m - %H:%M:%S'),
                #'LCOStatus': lco_status,
                'Giờ vào': fci.strftime('%d/%m - %H:%M:%S'),
                'Giờ ra': lco.strftime('%d/%m - %H:%M:%S'),
                'Thời lượng (h)': round(duration, 2),
                'Thời lượng': format_duration(duration),
                'Loại ca': shift_type,
                'Log hôm trước': prev_log_info
            })

            i = j if found_lco else i + 1

        handle_single_logs(group, processed_indices, emp_id, name, records)

    df_result = pd.DataFrame(records)
    # df_result = handle_machine_failure(df_result)

    df_result['FCI (giờ)'] = df_result['FirstCheckIn'].apply(extract_time_only)
    df_result['LCO (giờ)'] = df_result['LastCheckOut'].apply(extract_time_only)

    df_result['Ghi chú'] = ""
    df_result = df_result[[
        'ID', 'Họ tên', 'Ngày chấm công',
        'Giờ vào', 'Giờ ra',
        'FirstCheckIn', 'FCI (giờ)',
        'LastCheckOut', 'LCO (giờ)',
        'Thời lượng (h)', 'Thời lượng', 'Loại ca',
        'Ghi chú'
    ]]
    df_result.sort_values(by='ID', key=lambda x: x.map(natural_sort_key), inplace=True)

    # Loại bỏ các dòng trùng lặp 100% dựa trên các cột quan trọng
    df_result = df_result.drop_duplicates(subset=['ID', 'Ngày chấm công', 'FirstCheckIn', 'LastCheckOut', 'Loại ca'], keep='first')

    # Áp dụng điều chỉnh chính sách nếu có policy_df
    if policy_df is not None:
        df_result, summary_df = apply_policy_adjustments(df_result, policy_df)
        # Gộp summary_df vào df_result để thêm cột tổng đi trễ/về sớm
        df_result = df_result.merge(summary_df, on='ID', how='left')
        # Điền giá trị 0 cho các nhân viên không có dữ liệu đi trễ/về sớm
        # Áp dụng format_duration cho Tổng đi trễ (phút) và Tổng về sớm (phút)

        # df_result['Tổng đi trễ (phút)'] = df_result['Tổng đi trễ (phút)'].fillna(0)
        # df_result['Tổng về sớm (phút)'] = df_result['Tổng về sớm (phút)'].fillna(0)

        df_result['Tổng đi trễ (phút)'] = df_result['Tổng đi trễ (phút)'].apply(lambda x: format_duration(x / 60))
        df_result['Tổng về sớm (phút)'] = df_result['Tổng về sớm (phút)'].apply(lambda x: format_duration(x / 60))

    # Loại bỏ các dòng có NaN trong các cột quan trọng
    # df_result = remove_nan_rows(df_result)

    return df_result