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
    var url = "/delete/"+li.id.replace("_","/");
    http.open("GET", url);
    http.send();

    li.remove();
}
