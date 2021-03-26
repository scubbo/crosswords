$(document).ready(function() {
    $('.datepicker').datepicker({dateFormat: 'yy-mm-dd'});
    reset_graph()
    $('#reset_graph').click(function() {
        reset_graph($('#start_date_picker').val(), $('#end_date_picker').val(), $('#statistic_picker').val())
    })
});

function reset_graph(start_date, end_date, statistic) {
    args = {}
    if (start_date !== undefined) {
        args['date_range'] = start_date + '_' + end_date
    }
    if (statistic !== undefined) {
        args['statistic'] = statistic
    }

    $.get('/api/get_data',
        args,
        function(data) {

        var ctx = document.getElementById('scoreChart').getContext('2d');
        datasets = []

        // I stole these from https://venngage.com/blog/color-blind-friendly-palette -
        // but, not being colour-blind myself, I can't test them
        // for suitability.
        // TODO - more colours (will be necessary to
        // display more than four players' scores!)
        colours = ['#0f2080', '#85c0f9', '#a95aa1', '#f5793a']

        // Renaming and restructing from what makes sense for the API,
        // to what chart.js expects.
        // If Javascript has dict-comprehensions like Python,
        // please let me know!
        for (name in data['scores']) {
            datasets.push({
                label: name,
                data: data['scores'][name],
                fill: false,
                borderColor: colours.pop()
            })
        }
        var myChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data['dates'],
                datasets: datasets
            },
        });
        // I don't know why, but graph.js seems to override the canvas' `width/height` values
        $('#scoreChart').css('height', 800);
        $('#scoreChart').css('width', 1600);
    });
}