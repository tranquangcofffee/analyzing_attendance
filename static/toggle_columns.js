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
