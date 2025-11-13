import os
from flask import Flask, request, render_template, redirect, url_for, send_file
from flask_caching import Cache
from datetime import datetime
import pandas as pd
from services.attendance_service import process_attendance, format_duration
from services.excel_service import save_excel, get_excel_path
from services.add_log_service import add_log_service, reconstruct_raw_data_from_attendance
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import NamedStyle
from io import BytesIO
from math import ceil
import re

app = Flask(__name__)
df_result = pd.DataFrame()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60 * 8 # giữ cache 1 giờ
cache = Cache(app)

def reload_raw_data():
    filename = cache.get('raw_data_filename')
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath, encoding='utf-8-sig')
            else:
                df = pd.read_excel(filepath)
            print(f"Reloaded raw_data columns: {df.columns.tolist()}")
            cache.set('raw_data', df.to_dict(orient='records'))
            return df
        except Exception as e:
            print(f"Error reloading raw_data: {e}")
    return None

def sort_attendance_df(df):
    df_regular = df[~df['ID'].astype(str).str.startswith('OUTSIDE_')].copy()
    df_outside = df[df['ID'].astype(str).str.startswith('OUTSIDE_')].copy()

    # Sắp theo ID số (đối với nhân viên thường)
    df_regular['ID_sort'] = df_regular['ID'].astype(int)

    # Sắp theo số sau OUTSIDE_ (ví dụ OUTSIDE_3 -> 3)
    df_outside['ID_sort'] = df_outside['ID'].astype(str).str.extract(r'OUTSIDE_(\d+)').astype(int)

    # Sắp theo ID_sort và Ngày chấm công
    df_regular = df_regular.sort_values(by=['ID_sort', 'Ngày chấm công'])
    df_outside = df_outside.sort_values(by=['ID_sort', 'Ngày chấm công'])

    # Gộp lại, nhân viên thường trước
    df_sorted = pd.concat([df_regular, df_outside], ignore_index=True)

    return df_sorted.drop(columns=['ID_sort'])

def filter_by_date(df, start_date=None, end_date=None):
    """Lọc DataFrame theo khoảng ngày, hỗ trợ định dạng MM/dd/yyyy (HTML) và yyyy-mm-dd (GET)."""
    if not start_date and not end_date:
        return df, {}

    # Debug: In giá trị đầu vào và các giá trị trong Ngày chấm công
    print(f"Filtering with start_date: {start_date}, end_date: {end_date}")
    print(f"Ngày chấm công values: {df['Ngày chấm công'].unique()}")

    # Chuyển đổi Ngày chấm công sang datetime
    try:
        df['Ngày chấm công_dt'] = pd.to_datetime(df['Ngày chấm công'], format='%d/%m/%Y', dayfirst=True)
    except Exception as e:
        print(f"Error parsing Ngày chấm công: {e}")
        df['Ngày chấm công_dt'] = pd.to_datetime(df['Ngày chấm công'], errors='coerce')
        if df['Ngày chấm công_dt'].isna().any():
            print(f"Warning: Some Ngày chấm công values could not be parsed: {df[df['Ngày chấm công_dt'].isna()]['Ngày chấm công']}")
            return df, {}

    # Danh sách định dạng ngày được hỗ trợ cho start_date và end_date
    date_formats = ['%m/%d/%Y', '%Y-%m-%d']

    # Lọc theo start_date
    if start_date:
        start_date_dt = None
        for fmt in date_formats:
            try:
                start_date_dt = pd.to_datetime(start_date, format=fmt)
                print(f"Parsed start_date: {start_date_dt} (format: {fmt})")
                df = df[df['Ngày chấm công_dt'] >= start_date_dt]
                break
            except ValueError:
                continue
        if start_date_dt is None:
            raise ValueError("Định dạng ngày bắt đầu không hợp lệ. Vui lòng nhập theo định dạng MM/dd/yyyy hoặc yyyy-mm-dd.")

    # Lọc theo end_date
    if end_date:
        end_date_dt = None
        for fmt in date_formats:
            try:
                end_date_dt = pd.to_datetime(end_date, format=fmt)
                print(f"Parsed end_date: {end_date_dt} (format: {fmt})")
                df = df[df['Ngày chấm công_dt'] <= end_date_dt]
                break
            except ValueError:
                continue
        if end_date_dt is None:
            raise ValueError("Định dạng ngày kết thúc không hợp lệ. Vui lòng nhập theo định dạng MM/dd/yyyy hoặc yyyy-mm-dd.")

    # Tính toán thống kê
    stats = {
        'total_late': df['Đi trễ/Về sớm'].str.contains('Đi trễ').sum(),
        'total_early': df['Đi trễ/Về sớm'].str.contains('Về sớm').sum(),
        'total_on_time': (df['Đi trễ/Về sớm'] == 'Đúng giờ').sum(),
        'total_missing': df['Đi trễ/Về sớm'].str.contains('Thiếu').sum()
    }

    # Xóa cột tạm
    df = df.drop(columns=['Ngày chấm công_dt'])
    return df, stats

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    total_duration = None  # Khởi tạo ngoài để tránh lỗi khi không có dữ liệu
    stats = {}  # Thống kê đi trễ, về sớm, đúng giờ, thiếu log
    late_employees = []  # Danh sách nhân sự đi trễ
    missing_employees = []  # Danh sách nhân sự quét thiếu
    early_employees = []  # Danh sách nhân sự về sớm
    total_pages = 0  # Initialize default value
    total_records = 0  # Initialize default value

    # Thêm tham số phân trang
    page = max(1, int(request.args.get('page', 1)))
    per_page = max(10, min(int(request.args.get('per_page', 500)), 100))

    if request.method == 'POST':
        file = request.files['file']
        policy_file = request.files.get('policy_file')

        filename = file.filename.lower()
        policy_df = None

        if file and (filename.endswith('.csv') or filename.endswith('.xlsx')):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            try:
                # Đọc file chấm công
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath, encoding='utf-8-sig')
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(filepath)
                else:
                    df = pd.read_excel(filepath)
            except Exception as e:
                return f"Lỗi khi đọc file chấm công: {str(e)}"

            # Nếu có file policy -> đọc
            if policy_file and policy_file.filename.endswith('.xlsx'):
                policy_path = os.path.join(app.config['UPLOAD_FOLDER'], policy_file.filename)
                policy_file.save(policy_path)

                try:
                    policy_df = pd.read_excel(policy_path)
                except Exception as e:
                    return f"Lỗi khi đọc file policy: {str(e)}"

            # Gọi hàm xử lý
            result = process_attendance(df, policy_df)
            cache.set('attendance_data', result)
            cache.set('raw_data', df.to_dict(orient='records'))
            cache.set('policy_data', policy_df.to_dict(orient='records') if policy_df is not None else None)

            # Ghi ra file
            save_excel(result)

        else:
            return "Chỉ hỗ trợ file .csv hoặc .xlsx"

    # GET: lọc dữ liệu từ cache
    cached_df = cache.get('attendance_data')

    if cached_df is not None:
        df = cached_df.copy()

        policy_data = cache.get('policy_data')
        working_places = []
        if policy_data is not None:
            policy_df = pd.DataFrame(policy_data)
            working_places = policy_df['working_place'].dropna().str.strip().str.title().unique().tolist()
            # Loại bỏ giá trị rỗng
            working_places = [place for place in working_places if place]
        else:
            # Nếu không có policy_data, sử dụng giá trị mặc định hoặc từ df
            working_places = [place for place in df['Nơi làm việc'].unique() if place and place != 'Không xác định']
            print("Warning: No policy_data found, falling back to df['Nơi làm việc']")

        msnv = request.args.get('msnv', '').strip()
        name = request.args.get('name', '').strip().lower()
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        shift_types = request.args.getlist('shift_type[]')  # Lấy danh sách shift_type
        working_place = request.args.getlist('working_place[]')  # Lấy danh sách nơi làm việc

        # Lọc theo loại ca
        if shift_types:
            df = df[df['Loại ca'].isin(shift_types)]
        if msnv:
            df = df[df['ID'].astype(str) == msnv]
        if name:
            df = df[df['Họ tên'].str.lower() == name]
        # Lọc theo nơi làm việc
        if working_place:
            print(f"Filtering by working_place: {working_place}")
            print(f"Available working_places: {working_places}")
            valid_places = [place for place in working_place if place in working_places]
            if not valid_places:
                return render_template('index.html', 
                                     error="Không có nơi làm việc nào trong danh sách lựa chọn tồn tại trong dữ liệu.", 
                                     working_places=working_places)
            df = df[df['Nơi làm việc'].isin(valid_places)]
            print(f"Rows after filtering by working_place: {len(df)}")

        # Lọc theo ngày sử dụng filter_by_date
        try:
            df, stats = filter_by_date(df, start_date, end_date)
        except ValueError as e:
            return str(e)

        if msnv or name or start_date or end_date:
            total_seconds = int(df['Thời lượng (h)'].sum() * 3600)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            total_duration = f"{hours} giờ {minutes} phút"

        try:
            df['ID_sort'] = df['ID'].apply(lambda x: int(str(x).split('_')[-1]) if 'OUTSIDE_' in str(x) else int(x))
        except ValueError:
            df['ID_sort'] = df['ID']  # fallback nếu có lỗi

        df = df.sort_values(by=['ID_sort', 'Ngày chấm công']).drop(columns=['ID_sort'])

        df = sort_attendance_df(df)
        # result = df

        # Tính toán phân trang
        total_records = len(df)
        total_pages = ceil(total_records / per_page)  # Tổng số trang
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        df_paginated = df.iloc[start_idx:end_idx]  # Lấy dữ liệu cho trang hiện tại
        print(f"Pagination: total_records={total_records}, total_pages={total_pages}, start_idx={start_idx}, end_idx={end_idx}")

        # Khởi tạo biến đếm số lần
        total_late = 0
        total_early = 0
        total_missing = 0
        total_on_time = 0

        # Duyệt qua từng hàng trong DataFrame
        for index, row in df.iterrows():
            status = row['Đi trễ/Về sớm']
            if pd.notna(status):
                # Tách các trạng thái (nếu có nhiều trạng thái trong cùng một ca)
                statuses = status.split(', ')
                for s in statuses:
                    if 'Đi trễ' in s:
                        total_late += 1
                    elif 'Về sớm' in s:
                        total_early += 1
                    elif 'Thiếu log' in s:
                        total_missing += 1
                    elif 'Đúng giờ' in s:
                        total_on_time += 1

        # Lọc ra danh sách nhân sự đi trễ, về sớm và quét thiếu
        late_employees = df[df['Đi trễ/Về sớm'].str.contains('Đi trễ', na=False)]['Họ tên'].unique().tolist()
        early_employees = df[df['Đi trễ/Về sớm'].str.contains('Về sớm', na=False)]['Họ tên'].unique().tolist()
        missing_employees = df[df['Đi trễ/Về sớm'].str.contains('Thiếu log', na=False)]['Họ tên'].unique().tolist()

        # Tính tổng thời gian đi trễ và về sớm từ cột 'Đi trễ/Về sớm'
        total_late_minutes = 0
        total_early_minutes = 0

        import re  # Đảm bảo import re ở đầu file
        for index, row in df.iterrows():
            status = row['Đi trễ/Về sớm']
            if pd.notna(status) and status != "Đúng giờ":
                statuses = status.split(', ') if ', ' in status else [status]
                for s in statuses:
                    s = s.strip()
                    if s.startswith('Đi trễ'):
                        match = re.search(r'Đi trễ\s*(-?\d+)', s)
                        if match:
                            minutes = int(match.group(1))
                            total_late_minutes += minutes
                    elif s.startswith('Về sớm'):
                        match = re.search(r'Về sớm\s*(-?\d+)', s)
                        if match:
                            minutes = int(match.group(1))
                            total_early_minutes += minutes

        # Làm sạch dữ liệu trước khi xử lý
        df['Đi trễ/Về sớm'] = df['Đi trễ/Về sớm'].fillna('Đúng giờ').str.strip()

        for index, row in df.iterrows():
            status = row['Đi trễ/Về sớm']
            if pd.notna(status):  # Chỉ xử lý nếu status không phải NaN
                # Tách các trạng thái, đảm bảo xử lý đúng khi không có dấu phẩy
                statuses = status.split(', ') if ', ' in status else [status]
                for s in statuses:
                    s = s.strip()
                    if 'Đi trễ' in s:
                        total_late += 1
                        minutes_str = s.replace('Đi trễ ', '').replace(' phút', '').strip()
                        if minutes_str.isdigit():
                            minutes = int(minutes_str)
                            total_late_minutes += minutes
                    elif 'Về sớm' in s:
                        total_early += 1
                        minutes_str = s.replace('Về sớm ', '').replace(' phút', '').strip()
                        if minutes_str.isdigit():
                            minutes = int(minutes_str)
                            total_early_minutes += minutes
                    elif 'Thiếu' in s:
                        total_missing += 1
                    elif 'Đúng giờ' in s:
                        total_on_time += 1

        # Chuyển đổi tổng thời gian thành định dạng giờ:phút
        total_late_hours = total_late_minutes // 60
        total_late_minutes_rem = total_late_minutes % 60
        total_early_hours = total_early_minutes // 60
        total_early_minutes_rem = total_early_minutes % 60
        total_late_duration = f"{total_late_hours} giờ {total_late_minutes_rem} phút" if total_late_minutes > 0 else "0 phút"
        total_early_duration = f"{total_early_hours} giờ {total_early_minutes_rem} phút" if total_early_minutes > 0 else "0 phút"

        # Cập nhật thống kê
        # stats.update({
        #     'total_late': len(late_employees),
        #     'total_early': len(early_employees),
        #     'total_missing': len(missing_employees),
        #     'total_on_time': len(df) - len(late_employees) - len(early_employees) - len(missing_employees),
        #     'total_late_duration': total_late_duration,
        #     'total_early_duration': total_early_duration
        # })

        # Cập nhật stats
        stats.update({
            'total_late': total_late,  # Số lần đi trễ
            'total_early': total_early,  # Số lần về sớm
            'total_missing': total_missing,  # Số lần quét thiếu
            'total_on_time': total_on_time,  # Số lần đúng giờ
            'total_late_duration': total_late_duration,  # Giữ nguyên vì đã đúng
            'total_early_duration': total_early_duration  # Giữ nguyên vì đã đúng
        })

        result = df_paginated

    return render_template('index.html',
        tables=[result.to_html(classes='data', index=False, escape=False)] if result is not None else None,
        titles=result.columns.values if result is not None else None,
        result=result if result is not None else pd.DataFrame(),
        total_duration=total_duration if result is not None else None,
        stats=stats,
        late_employees=late_employees,
        missing_employees=missing_employees,
        early_employees=early_employees if early_employees else [],
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_records=total_records
        # working_places=working_places,
    )

@app.route('/add_log', methods=['POST'])
def add_log():
    cache_status = {
        'raw_data': cache.get('raw_data') is not None,
        'policy_data': cache.get('policy_data') is not None,
        'attendance_data': cache.get('attendance_data') is not None
    }
    print(f"Cache check in /add_log: {cache_status}")

    raw_data = cache.get('raw_data')
    if raw_data is None:
        df = reload_raw_data()
        if df is not None:
            raw_data = df.to_dict(orient='records')
            cache.set('raw_data', raw_data)
        else:
            attendance_data = cache.get('attendance_data')
            raw_data = reconstruct_raw_data_from_attendance(attendance_data)
            if raw_data is None:
                return render_template('index.html', 
                                     error="Dữ liệu chấm công gốc không có và không thể tái tạo. Vui lòng upload lại file chấm công.", 
                                     cache_status=cache_status), 400
            cache.set('raw_data', raw_data)
    
    policy_data = cache.get('policy_data')
    
    id_emp = request.form.get('id').strip()
    datetime_str = request.form.get('datetime')
    key = request.form.get('key')
    
    raw_df, result_df, error = add_log_service(raw_data, policy_data, id_emp, datetime_str, key)
    
    if error:
        return render_template('index.html', error=error, cache_status=cache_status), 400
    
    cache.set('raw_data', raw_df.to_dict(orient='records'))
    cache.set('attendance_data', result_df)
    save_excel(result_df)
    
    return redirect(url_for('index'))

@app.route('/download', methods=['GET', 'POST'])
def download_excel():
    # Lấy dữ liệu
    df = cache.get('attendance_data')
    if df is None:
        return "Không có dữ liệu để tải.", 400
    
    # Lấy danh sách nơi làm việc từ policy_data
    policy_data = cache.get('policy_data')
    working_places = []
    if policy_data is not None:
        policy_df = pd.DataFrame(policy_data)
        working_places = policy_df['working_place'].dropna().str.strip().str.title().unique().tolist()
        working_places = [place for place in working_places if place]
    else:
        working_places = ['Không xác định']
        print("Warning: No policy_data found, using default working_places")

    # Xử lý nguồn dữ liệu đầu vào
    if request.method == 'POST':
        visible_cols_str = request.form.get('visible_columns', '')
        working_place = request.form.getlist('working_place[]')
        shift_types = request.form.getlist('shift_type[]')
        employee_id = request.form.get('employee_id', '').strip()
        name = request.form.get('name', '').strip().lower()
        start_date = request.form.get('start_date', '').strip()  # Thêm start_date
        end_date = request.form.get('end_date', '').strip()      # Thêm end_date
    else:  # GET
        visible_cols_str = request.args.get('visible_columns', '')
        working_place = request.form.getlist('working_place[]')
        shift_types = request.args.getlist('shift_type[]')
        employee_id = request.args.get('employee_id', '').strip()
        name = request.args.get('name', '').strip().lower()
        start_date = request.args.get('start_date', '').strip()  # Thêm start_date
        end_date = request.args.get('end_date', '').strip()      # Thêm end_date

    # Lọc dữ liệu nếu có shift_type, ID hoặc ngày
    df_filtered = df.copy()

    # Đảm bảo cột Nơi làm việc tồn tại
    if 'Nơi làm việc' not in df_filtered.columns:
        df_filtered['Nơi làm việc'] = 'Không xác định'
    # Xử lý giá trị rỗng trong Nơi làm việc
    df_filtered['Nơi làm việc'] = df_filtered['Nơi làm việc'].replace('', 'Không xác định')

    if shift_types:
        df_filtered = df_filtered[df_filtered['Loại ca'].isin(shift_types)]

    if working_place:
        valid_places = [place for place in working_place if place in working_places or place == 'Không xác định']
        if valid_places:
            df_filtered = df_filtered[df_filtered['Nơi làm việc'].isin(valid_places)]

    if employee_id:
        df_filtered = df_filtered[df_filtered['ID'].astype(str) == employee_id]

    # Lọc theo ngày nếu có start_date và end_date
    if start_date or end_date:
        # Chuyển cột 'Ngày chấm công' sang datetime nếu chưa phải
        df_filtered['Ngày chấm công'] = pd.to_datetime(df_filtered['Ngày chấm công'], format='%d/%m/%Y', errors='coerce')
        
        # Xử lý start_date và end_date
        if start_date:
            start_date = pd.to_datetime(start_date, format='%Y-%m-%d', errors='coerce').replace(hour=0, minute=0, second=0)
        if end_date:
            end_date = pd.to_datetime(end_date, format='%Y-%m-%d', errors='coerce')
            if start_date and end_date == start_date:  # Nếu cùng ngày, mở rộng end_date
                end_date = end_date.replace(hour=23, minute=59, second=59)
            else:
                end_date = end_date.replace(hour=23, minute=59, second=59)
        
        # Áp dụng lọc
        mask = pd.Series(True, index=df_filtered.index)
        if start_date and end_date:
            mask = (df_filtered['Ngày chấm công'] >= start_date) & (df_filtered['Ngày chấm công'] <= end_date)
        elif start_date:
            mask = df_filtered['Ngày chấm công'] >= start_date
        elif end_date:
            mask = df_filtered['Ngày chấm công'] <= end_date
        df_filtered = df_filtered[mask]

    # Kiểm tra nếu không có dữ liệu sau khi lọc
    if df_filtered.empty:
        return "Không có dữ liệu cho khoảng ngày được chọn.", 400

    # Sắp xếp theo ID (ID dạng số trước, ID chứa OUTSIDE cuối) và Ngày chấm công
    if 'ID' in df_filtered.columns and 'Ngày chấm công' in df_filtered.columns:
        # Hàm trích xuất phần số từ ID
        def extract_number(id_str):
            if isinstance(id_str, str) and 'OUTSIDE' in id_str.upper():
                return float('inf')  # Đặt OUTSIDE xuống cuối
            try:
                return int(id_str)  # Thử chuyển thành số
            except (ValueError, TypeError):
                return float('inf')  # Nếu không phải số, đặt xuống cuối

        # Tạo cột tạm cho sắp xếp
        df_filtered['ID_number'] = df_filtered['ID'].apply(extract_number)
        df_filtered['ID_is_outside'] = df_filtered['ID'].apply(lambda x: isinstance(x, str) and 'OUTSIDE' in x.upper())
        df_filtered = df_filtered.sort_values(by=['ID_is_outside', 'ID_number', 'ID', 'Ngày chấm công'], ascending=[True, True, True, True])
        df_filtered = df_filtered.drop(columns=['ID_number', 'ID_is_outside'])  # Xóa cột tạm

    # Tính thời lượng nếu có
    if 'Thời lượng (h)' in df_filtered.columns:
        df_filtered['Thời lượng'] = df_filtered['Thời lượng (h)'].apply(format_duration)

    # Chọn cột cần export
    visible_indices = list(map(int, visible_cols_str.split(','))) if visible_cols_str else []
    full_columns = df_filtered.columns.tolist()
    selected_columns = [full_columns[i] for i in visible_indices if i < len(full_columns)]
    df_final = df_filtered[selected_columns] if selected_columns else df_filtered

    # Tính tổng thời lượng (nếu lọc theo ID)
    total_duration = None
    if employee_id and 'Thời lượng (h)' in df_filtered.columns:
        total_seconds = int(df_filtered['Thời lượng (h)'].sum() * 3600)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_duration = f"{hours} giờ {minutes} phút"

    # Thêm dòng tổng
    if total_duration and 'Thời lượng' in df_final.columns:
        total_row = pd.DataFrame(
            [['Tổng thời lượng', total_duration]],
            columns=[df_final.columns[0], df_final.columns[-1]]
        )
        df_final = pd.concat([df_final, total_row], ignore_index=True)

    # Xuất file Excel với định dạng ngày
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Sheet1')
        # Lấy workbook và worksheet
        workbook = writer.book
        worksheet = writer.sheets['Sheet1']
        
        # Định dạng cột ngày
        date_style = NamedStyle(name='date_style', number_format='DD/MM/YYYY')
        if 'Ngày chấm công' in df_final.columns:
            col_idx = df_final.columns.get_loc('Ngày chấm công') + 1  # +1 vì Excel bắt đầu từ 1
            for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row, min_col=col_idx, max_col=col_idx):
                for cell in row:
                    cell.style = date_style

    output.seek(0)
    file_name = (employee_id + name if employee_id else "ket_qua_loc") + '.xlsx'
    return send_file(output, download_name=file_name, as_attachment=True)

@app.route('/download', methods=['GET'])
def download_filtered_excel():
    visible_cols_str = request.args.get('visible_columns', '')
    visible_indices = list(map(int, visible_cols_str.split(','))) if visible_cols_str else []

    shift_types = request.args.getlist('shift_type[]')  # Lấy danh sách shift_type
    working_place = request.form.getlist('working_place[]')  # Lấy danh sách nơi làm việc
    employee_id = request.args.get('employee_id', '').strip()
    name = request.args.get('name', '').strip().lower()

    file_name = employee_id + name

    df = cache.get('attendance_data')
    if df is None:
        return "Không có dữ liệu để tải.", 400
    
    # Lấy danh sách nơi làm việc từ policy_data
    policy_data = cache.get('policy_data')
    working_places = []
    if policy_data is not None:
        policy_df = pd.DataFrame(policy_data)
        working_places = policy_df['working_place'].dropna().str.strip().str.title().unique().tolist()
        working_places = [place for place in working_places if place]
    else:
        working_places = ['Không xác định']
        print("Warning: No policy_data found, using default working_places")

    df_filtered = df.copy()

    # Đảm bảo cột Nơi làm việc tồn tại
    if 'Nơi làm việc' not in df_filtered.columns:
        df_filtered['Nơi làm việc'] = 'Không xác định'
    
    # Xử lý giá trị rỗng trong Nơi làm việc
    df_filtered['Nơi làm việc'] = df_filtered['Nơi làm việc'].replace('', 'Không xác định')

    # Lọc theo loại ca (nếu có)
    if shift_types:
        df_filtered = df_filtered[df_filtered['Loại ca'].isin(shift_types)]

    if working_place:
        valid_places = [place for place in working_place if place in working_places or place == 'Không xác định']
        if valid_places:
            df_filtered = df_filtered[df_filtered['Nơi làm việc'].isin(valid_places)]

    # Lọc theo ID (nếu có)
    if employee_id:
        df_filtered = df_filtered[df_filtered['ID'].astype(str) == employee_id]

    # Tạo cột "Thời lượng" đẹp (giờ - phút)
    df_filtered['Thời lượng'] = df_filtered['Thời lượng (h)'].apply(format_duration)

    # Lấy đúng thứ tự cột như hiển thị HTML
    full_columns = df_filtered.columns.tolist()
    selected_columns = [full_columns[i] for i in visible_indices if i < len(full_columns)]
    df_final = df_filtered[selected_columns] if selected_columns else df_filtered

    total_duration = None
    if employee_id:
        total_seconds = int(df_filtered['Thời lượng (h)'].sum() * 3600)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_duration = f"{hours} giờ {minutes} phút"

    # Thêm dòng tổng thời lượng nếu có
    if total_duration and employee_id:
        # Tạo DataFrame cho dòng tổng
        total_row = pd.DataFrame([['Tổng thời lượng', total_duration] if 'Thời lượng' in df_final.columns else ['Tổng', total_duration]], 
                                columns=[df_final.columns[0], df_final.columns[-1]])
        df_final = pd.concat([df_final, total_row], ignore_index=True)

    output = BytesIO()
    df_final.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name=file_name + '.xlsx', as_attachment=True)

@app.route('/check_cache')
def check_cache():
    cache_status = {
        'raw_data': cache.get('raw_data') is not None,
        'policy_data': cache.get('policy_data') is not None,
        'attendance_data': cache.get('attendance_data') is not None
    }
    return render_template('cache_status.html', cache_status=cache_status)

@app.route('/update')
def update():
    return render_template('update.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
