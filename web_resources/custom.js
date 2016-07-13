function reloadTimeout() {
    var t;
    window.onload = resetTimer;
    document.onmousemove = resetTimer;
    document.onkeypress = resetTimer;
    var timerhtml = document.getElementById("timer");
    var outertimerhtml = document.getElementById("timertext");
    var counter = 10*60+1;
    timerhtml.innerHTML = `${(counter-counter%60)/60}m${counter%60}s`;

    function resetTimer() {
        counter = 10*60+1;
    }

    function countdown() {
        counter = counter - 1;
        timerhtml.innerHTML = `${(counter-counter%60)/60}m${counter%60}s`;
        if (counter==0) {
            clearInterval(t);
            outertimerhtml.innerHTML = "Refreshing now!"
            document.getElementById("dark_layer").style.display = "block";
            location.reload();
        }
    }

    t = setInterval(countdown, 1000)
};

function deleteNearestLI(arg) {
    var li = arg.parentElement;
    while (li.tagName != 'LI') {
        li = li.parentElement;
    }

    var http = new XMLHttpRequest();
    var url = "/do_delete";
    var table = li.id.split('_')[0];
    var entry = li.id.replace(table+'_','');
    http.open("POST", url);
    http.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    http.send(`table=${table}&entry=${entry}`);

    li.remove();
}

function addAndRefreshContainer(arg) {
    var form = arg.parentElement;
    var container = form.parentElement.parentElement;
    var note = form.getElementsByTagName("textarea")[0].value;
    var experiment = form.getElementsByTagName("input")[0].value;
    var t = document.createTextNode(note);

    var http = new XMLHttpRequest();
    http.onreadystatechange = function() {
      if (http.readyState == 4 && http.status == 200) {
        container.outerHTML = http.responseText;
      }
    };
    http.open("GET", `/do_add_note?experiment_name=${experiment}&note=${note}`);
    http.send();
}
