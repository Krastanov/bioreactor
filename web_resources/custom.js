function reloadTimeout() {
    var t;
    window.onload = resetTimer;
    document.onmousemove = resetTimer;
    document.onkeypress = resetTimer;

    function refresh() {
        document.getElementById("dark_layer").style.display = "";
        location.reload();
    }

    function resetTimer() {
        clearTimeout(t);
        t = setTimeout(refresh, 10*60*1000);
    }
};

function deleteNearestLI(arg) {
    var li = arg.parentElement;
    while (li.tagName != 'LI') {
        li = li.parentElement;
    }

    var http = new XMLHttpRequest();
    var url = "/do_delete";
    http.open("POST", url);
    http.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    http.send(`table=${li.id.split('_')[0]}&entry=${li.id.split('_')[1]}`);

    li.remove();
}

function addToNearestUL(arg) {
    var form = arg.parentElement;
    var div = form.parentElement;
    var ul = div.getElementsByTagName("UL")[0];
    var li = document.createElement("LI");
    var note = form.getElementsByTagName("textarea")[0].value;
    var experiment = form.getElementsByTagName("input")[0].value;
    var t = document.createTextNode(note);

    var http = new XMLHttpRequest();
    var url = "/do_add_note";
    http.open("POST", url);
    http.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    http.send(`experiment_name=${experiment}&note=${note}`);

    li.appendChild(t);
    ul.insertBefore(li, ul.firstChild);
}
