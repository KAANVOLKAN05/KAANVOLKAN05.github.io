let simulationData = [];
let columnNames = [];

fetch('data/summary.csv')
    .then(response => response.text())
    .then(text => {

        const lines = text.trim().split('\n');

        columnNames = lines[0].split(',');

        simulationData = lines.slice(1).map(line => {

            const values = line.split(',');
            const row = {};

            columnNames.forEach((column, i) => {

                if (column === 'RunID') {
                    row[column] = values[i];
                } else {
                    row[column] = Number(values[i]);
                }

            });

            return row;
        });

        document.getElementById('status').textContent =
            `Loaded ${simulationData.length} simulations.`;

        const xAxisSelect = document.getElementById('xAxis');
        const yAxisSelect = document.getElementById('yAxis');

        xAxisSelect.innerHTML = '';
        yAxisSelect.innerHTML = '';

        columnNames.forEach(column => {

            xAxisSelect.innerHTML +=
                `<option value="${column}">${column}</option>`;

            yAxisSelect.innerHTML +=
                `<option value="${column}">${column}</option>`;

        });

    });