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
    while (li.tagName != "LI") {
        li = li.parentElement;
    }

    var http = new XMLHttpRequest();
    var url = "/do_delete";
    var table = li.id.split("_")[0];
    var entry = li.id.replace(table+"_","");
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

function trackSchedule() {
    NodeList.prototype[Symbol.iterator] = Array.prototype[Symbol.iterator];
    HTMLCollection.prototype[Symbol.iterator] = Array.prototype[Symbol.iterator];
    trackScheduleCallback(false);
    setInterval(trackScheduleCallback, 1000);
}

function trackScheduleCallback(permitReloads=true) {
    var sched = document.getElementById("schedule");
    var times = sched.getElementsByTagName("TIME");
    var reload = false;
    for (var time of times) {
        var parsedTime = parseFloat(time.getAttribute("data-seconds"))-1;
        if (parsedTime < 0) {reload = true;}
        time.innerHTML = secondsToCountdownString(parsedTime);
        time.setAttribute("data-seconds", parsedTime);
    }
    var current = sched.getElementsByClassName("current-event");
    if (current.length > 0) {reload = true;}
    if (reload && permitReloads) {
        var http = new XMLHttpRequest();
        http.onreadystatechange = function() {
            if (http.readyState == 4 && http.status == 200) {
                sched.innerHTML = http.responseText;
                trackScheduleCallback(false);
            }
        };
        http.open("GET", "/schedule");
        http.send();
    }
    if (current.length+times.length == 0) {location.reload();}
}

function secondsToCountdownString(seconds) {
    if (seconds < 0) {
        return "waiting";
    } else {
        var min = Math.floor(seconds/60);
        var sec = Math.floor(seconds%60);
        if (min>0) {
            return `${min}min ${sec}sec`;
        } else {
            return `${sec}sec`;
        }
    }
}

function toggleEventInput(button, eventName) {
    var eventDiv = document.getElementById(eventName);
    if (eventDiv.style.display == "none") {
        eventDiv.style.display = "block";
        document.getElementById(eventName+"__check").checked = true;
        button.className += " pure-button-active";
    } else {
        eventDiv.style.display = "none";
        document.getElementById(eventName+"__check").checked = false;
        button.className = button.className.replace(" pure-button-active","");
    }
} 
