document.addEventListener("DOMContentLoaded", () => {
    const formatter = new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });
    document.querySelectorAll("time.local-datetime").forEach((el) => {
        const d = new Date(el.getAttribute("datetime"));
        if (!isNaN(d)) el.textContent = formatter.format(d);
    });
});
