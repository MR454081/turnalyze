// Dark Mode
// =============================
// Turnalyze Dashboard JS
// =============================

// ---------- Dark Mode ----------

const themeBtn = document.querySelector(".theme-btn");

if (themeBtn) {

    themeBtn.addEventListener("click", function () {

        document.body.classList.toggle("dark");

        if (document.body.classList.contains("dark")) {
            localStorage.setItem("theme", "dark");
        } else {
            localStorage.setItem("theme", "light");
        }

    });

}

// Load saved theme

window.addEventListener("load", function () {

    if (localStorage.getItem("theme") === "dark") {
        document.body.classList.add("dark");
    }

});

// ---------- File Upload ----------

const input = document.getElementById("fileInput");
const fileName = document.querySelector(".file-name");
const form = document.getElementById("dashboardUploadForm");
const analyzeBtn = document.getElementById("analyzeBtn");

if (input && fileName) {

    input.addEventListener("change", function () {

        if (this.files.length > 0) {

            fileName.textContent = this.files[0].name;

        } else {

            fileName.textContent = "No file selected";

        }

    });

}

if (analyzeBtn && form) {

    analyzeBtn.addEventListener("click", function () {

        if (input && input.files.length > 0) {

            form.submit();

        } else {

            const reportsUrl = analyzeBtn.getAttribute("data-reports-url") || "/reports";

            window.location.href = reportsUrl;

        }

    });

}