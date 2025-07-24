import os
from flask import Flask, request, render_template, redirect, url_for
import pandas as pd
from services.attendance_service import process_attendance

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.xlsx'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            df = pd.read_excel(filepath)
            result = process_attendance(df)
            return render_template('index.html', tables=[result.to_html(classes='data')], titles=result.columns.values)
        else:
            return "Chỉ hỗ trợ file .xlsx"
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
