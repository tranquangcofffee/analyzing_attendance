document.querySelectorAll('.toggle-col').forEach(function (checkbox) {
    checkbox.addEventListener('change', function () {
        const colIndex = parseInt(this.getAttribute('data-col'));
        const display = this.checked ? '' : 'none';

        document.querySelectorAll('table tr').forEach(function (row) {
            const cells = row.querySelectorAll('th, td');
            if (cells[colIndex]) {
                cells[colIndex].style.display = display;
            }
        });
    });
});

document.getElementById('download-form').addEventListener('submit', function (e) {
    const visibleCols = [];
    document.querySelectorAll('.toggle-col').forEach((checkbox, index) => {
        if (checkbox.checked) {
            visibleCols.push(index);
        }
    });
    document.getElementById('visible-columns').value = visibleCols.join(',');
});