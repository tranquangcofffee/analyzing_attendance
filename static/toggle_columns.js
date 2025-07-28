document.querySelectorAll('.toggle-col').forEach(function (checkbox) {
    checkbox.addEventListener('change', function () {
        const colIndex = parseInt(this.getAttribute('data-col'));
        const display = this.checked ? '' : 'none';

        document.querySelectorAll('table.dataframe tr').forEach(function (row) {
            const cells = row.querySelectorAll('th, td');
            if (cells[colIndex]) {
                cells[colIndex].style.display = display;
            }
        });
    });
});

document.getElementById('download-form').addEventListener('submit', function (e) {
    const visibleCols = [];
    document.querySelectorAll('.toggle-col:checked').forEach(checkbox => {
        const colIndex = parseInt(checkbox.getAttribute('data-col'));
        visibleCols.push(colIndex);
    });
    console.log('visibleCols:', visibleCols); // Gỡ lỗi
    document.getElementById('visible-columns').value = visibleCols.join(',');
});

// Gán cột hiển thị vào form lọc (GET)
document.getElementById('download-filter-form').addEventListener('submit', function (e) {
    const visibleCols = [];
    document.querySelectorAll('.toggle-col:checked').forEach(checkbox => {
        const colIndex = parseInt(checkbox.getAttribute('data-col'));
        visibleCols.push(colIndex);
    });
    document.getElementById('visible_columns_filter_input').value = visibleCols.join(',');
});
