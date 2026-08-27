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

        console.log(columnNames);
        console.log(simulationData[0]);
        const xAxisSelect = document.getElementById('xAxis');
        const yAxisSelect = document.getElementById('yAxis');

        columnNames.forEach(column => {

            const xOption = document.createElement('option');
            xOption.value = column;
            xOption.textContent = column;
            xAxisSelect.appendChild(xOption);

            const yOption = document.createElement('option');
            yOption.value = column;
            yOption.textContent = column;
            yAxisSelect.appendChild(yOption);

        });
    });
