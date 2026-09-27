(() => {
    const DEFAULT_IMAGE = "images/tommyforintroduction.jpeg";
    const DEFAULT_COURSES = JSON.parse(document.getElementById("default-course-data").content.textContent);

    const BULLET_FIELDS = [
        ["Personal Background", "personalBackground"],
        ["Professional Background", "professionalBackground"],
        ["Academic Background", "academicBackground"],
        ["Primary Work Computer (type, OS, and version:)", "primaryWorkComputer"],
        ["Primary Work Location", "primaryWorkLocation"],
        ["Alternate Computer & Location", "alternateComputerLocation"]
    ];

    const INITIAL_FOOTER_LINKS = [
        { label: "CLT Web", url: "https://webpages.charlotte.edu/tmcelro3/" },
        { label: "GitHub.io", url: "https://tmcelroy2202.github.io/" },
        { label: "GitHub", url: "https://github.com/tmcelroy2202/" },
        { label: "freeCodeCamp", url: "https://www.freecodecamp.org/thomas-mcelroy" },
        { label: "Codecademy", url: "https://www.codecademy.com/profiles/giga5446778097" },
        { label: "LinkedIn", url: "https://www.linkedin.com/in/thomas-mcelroy-b68bb4352/" }
    ];

    let uploadedImageData = "";
    let defaultImageData = "";
    let defaultImagePromise = Promise.resolve();
    let imageReadPromise = Promise.resolve();
    let imageReadToken = 0;
    let courseNumber = 0;

    const escapeHTML = (value) => String(value === null || value === undefined ? "" : value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const getValue = (name) => document.querySelector(`[name="${name}"]`).value.trim();

    function updateCourseLegends() {
        document.querySelectorAll("[data-course-row] legend").forEach((legend, index) => {
            legend.textContent = `Course ${index + 1}`;
        });
    }

    function addCourse(course = {}) {
        const list = document.getElementById("course-list");
        const id = `course-${++courseNumber}`;
        const row = document.createElement("fieldset");
        row.className = "course-row form-grid";
        row.dataset.courseRow = "";
        row.innerHTML = `
            <legend>Course</legend>
            <label for="${id}-department">Department
            <input id="${id}-department" name="department" type="text" value="${escapeHTML(course.department || "")}" placeholder="e.g. ITIS" required>
            </label>
            <label for="${id}-number">Course number
                <input id="${id}-number" name="courseNumber" type="text" value="${escapeHTML(course.courseNumber || "")}" placeholder="e.g. 3135" required>
            </label>
            <label for="${id}-title">Course title
                <input id="${id}-title" name="courseTitle" type="text" value="${escapeHTML(course.courseTitle || "")}" placeholder="Course title" required>
            </label>
            <label for="${id}-reason">Reason for taking it
            <textarea id="${id}-reason" name="reasonForTaking" rows="3" placeholder="Why you're taking this course" required>${escapeHTML(course.reasonForTaking || "")}</textarea>
            </label>
            <button type="button" data-remove-course>Delete Course</button>
        `;
        list.append(row);
        updateCourseLegends();
    }

    function readCourses() {
        return [...document.querySelectorAll("[data-course-row]")].map((row) => ({
            department: row.querySelector('[name="department"]').value.trim(),
            courseNumber: row.querySelector('[name="courseNumber"]').value.trim(),
            courseTitle: row.querySelector('[name="courseTitle"]').value.trim(),
            reasonForTaking: row.querySelector('[name="reasonForTaking"]').value.trim()
        }));
    }

    function readData() {
        const footerLinks = INITIAL_FOOTER_LINKS.map((link, index) => ({
            label: getValue(`footerLabel${index + 1}`),
            url: getValue(`footerUrl${index + 1}`)
        }));

        return {
            firstName: getValue("firstName"),
            middleName: getValue("middleName"),
            nickname: getValue("nickname"),
            lastName: getValue("lastName"),
            acknowledgment: getValue("acknowledgment"),
            acknowledgmentDate: getValue("acknowledgmentDate"),
            prettyNameDivider: getValue("prettyNameDivider"),
            adjectives: getValue("adjectives"),
            animal: getValue("animal"),
            img: uploadedImageData || getValue("img"),
            pictureAlt: getValue("pictureAlt"),
            caption: getValue("caption"),
            personalInfo: {
                statement: getValue("personalStatement"),
                ...Object.fromEntries(BULLET_FIELDS.map(([, name]) => [name, getValue(name)]))
            },
            courses: readCourses(),
            quote: getValue("quote"),
            quoteAuthor: getValue("quoteAuthor"),
            funnyItem: getValue("funnyItem"),
            somethingToShare: getValue("somethingToShare"),
            footerLinks
        };
    }

    function displayName(data) {
        const parts = [data.firstName];
        if (data.middleName) {
            parts.push(data.middleName.endsWith(".") ? data.middleName : `${data.middleName}.`);
        }
        if (data.nickname) {
            parts.push(`"${data.nickname}"`);
        }
        if (data.lastName) {
            parts.push(data.lastName);
        }
        const divider = data.prettyNameDivider ? ` ${data.prettyNameDivider} ` : " ";
        return `${parts.filter(Boolean).join(" ")}${divider}${[data.adjectives, data.animal].filter(Boolean).join(" ")}`;
    }

    function formatDate(date) {
        if (!date) {
            return "";
        }
        let year;
        let month;
        let day;
        if (date.indexOf("-") !== -1) {
            [year, month, day] = date.split("-");
        } else {
            [month, day, year] = date.split("/");
        }
        return `${Number(month)}/${Number(day)}/${year.slice(-2)}`;
    }

    function renderIntroduction(data) {
        const acknowledgment = `${data.acknowledgment} - TM ${formatDate(data.acknowledgmentDate)}`
            .replaceAll("--", "—");
        const courses = data.courses.map((course) => (
            `<li><strong>${escapeHTML(course.department)}${escapeHTML(course.courseNumber)} - ${escapeHTML(course.courseTitle)}:</strong> ${escapeHTML(course.reasonForTaking)}</li>`
        )).join("\n            ");
        const optionalBullets = [
            data.funnyItem ? `<li><strong>Funny / Interesting Item to Remember Me by:</strong> ${escapeHTML(data.funnyItem)}</li>` : "",
            data.somethingToShare ? `<li><strong>I’d Also Like to Share:</strong> ${escapeHTML(data.somethingToShare)}</li>` : ""
        ].filter(Boolean).join("\n          ");

        return `<!-- ${acknowledgment} -->
<h6 class="centered" id="display-name">${escapeHTML(displayName(data))}</h6>
<figure>
  <img src="${escapeHTML(data.img)}" alt="${escapeHTML(data.pictureAlt)}">
  <figcaption class="centered">${escapeHTML(data.caption)}</figcaption>
</figure>
<p>${escapeHTML(data.personalInfo.statement)}</p>
<ul>
  ${BULLET_FIELDS.map(([label, name]) => `<li><strong>${escapeHTML(label)}:</strong> ${escapeHTML(data.personalInfo[name])}</li>`).join("\n  ")}
  <li><strong>Courses I'm Taking, &amp; Why:</strong>
    <ol>
      ${courses}
    </ol>
  </li>${optionalBullets ? `\n  ${optionalBullets}` : ""}
</ul>
<blockquote>${escapeHTML(data.quote)}</blockquote>
<p>- ${escapeHTML(data.quoteAuthor)}</p>`;
    }

    function renderFooter(data) {
        const links = data.footerLinks.map((link) => (
            `<a href="${escapeHTML(link.url)}">${escapeHTML(link.label)}</a>`
        )).join(" |  ");

        return `<footer>
    <nav>
        <p>${links}</p>
    </nav>
    <p>A product of <a href="./tommydoes.design/index.html">Tommy Does Design</a>, Certified in ©2026</p>
    <em>You are all better than you think you are. You are designed not to believe it when you hear it from yourself.</em>
</footer>`;
    }

    function renderHTMLDocument(data) {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thomas McElroy's Terrific Muskrat | ITIS3135 | Introduction Form</title>
    <link rel="stylesheet" href="styles/default.css">
    <link rel="icon" href="images/tommyfavicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Mono:wght@100..900&display=swap" rel="stylesheet">
    <script src="https://divonbriesen.github.io/teaching/tools/standards-check.js" defer></script>
    <script src="https://lint.page/kit/4d0fe3.js" crossorigin="anonymous"></script>
</head>
<body>
    <!-- This div inserts the shared header; classes and ids in the generated introduction apply the site's styles and identify its display name. -->
    <div data-include="components/header.html"></div>
    <main>
        <h2>Introduction Form</h2>
${renderIntroduction(data)}
${renderFooter(data)}
    </main>
    <script src="scripts/HTMLInclude.min.js"></script>
</body>
</html>`;
    }

    function renderXML(data) {
        const xmlEscape = (value) => String(value === null || value === undefined ? "" : value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&apos;");
        const tag = (name, value) => `    <${name}>${xmlEscape(value)}</${name}>`;
        const bulletXML = BULLET_FIELDS.map(([, name]) => tag(name, data.personalInfo[name])).join("\n");
        const courseXML = data.courses.map((course) => `      <course>
${tag("department", course.department).replace(/^    /gm, "        ")}
${tag("courseNumber", course.courseNumber).replace(/^    /gm, "        ")}
${tag("courseTitle", course.courseTitle).replace(/^    /gm, "        ")}
${tag("reasonForTaking", course.reasonForTaking).replace(/^    /gm, "        ")}
      </course>`).join("\n");
        const footerXML = data.footerLinks.map((link) => `      <link>
        <label>${xmlEscape(link.label)}</label>
        <url>${xmlEscape(link.url)}</url>
      </link>`).join("\n");

        return `<?xml version="1.0" encoding="UTF-8"?>
<introduction>
  <identity>
${tag("firstName", data.firstName).replace(/^    /gm, "    ")}
${tag("middleName", data.middleName).replace(/^    /gm, "    ")}
${tag("nickname", data.nickname).replace(/^    /gm, "    ")}
${tag("lastName", data.lastName).replace(/^    /gm, "    ")}
${tag("prettyNameDivider", data.prettyNameDivider).replace(/^    /gm, "    ")}
${tag("displayName", displayName(data)).replace(/^    /gm, "    ")}
  </identity>
  <acknowledgment>
${tag("statement", data.acknowledgment).replace(/^    /gm, "    ")}
${tag("date", data.acknowledgmentDate).replace(/^    /gm, "    ")}
  </acknowledgment>
  <mascot>
${tag("adjectives", data.adjectives).replace(/^    /gm, "    ")}
${tag("animal", data.animal).replace(/^    /gm, "    ")}
  </mascot>
  <picture>
${tag("img", data.img).replace(/^    /gm, "    ")}
${tag("alt", data.pictureAlt).replace(/^    /gm, "    ")}
${tag("caption", data.caption).replace(/^    /gm, "    ")}
  </picture>
  <personalInfo>
${tag("statement", data.personalInfo.statement).replace(/^    /gm, "    ")}
${bulletXML}
  </personalInfo>
  <courses>
${courseXML}
  </courses>
  <quote>
${tag("text", data.quote).replace(/^    /gm, "    ")}
${tag("author", data.quoteAuthor).replace(/^    /gm, "    ")}
  </quote>
${tag("funnyItem", data.funnyItem).replace(/^    /gm, "  ")}
${tag("somethingToShare", data.somethingToShare).replace(/^    /gm, "  ")}
  <footerLinks>
${footerXML}
  </footerLinks>
</introduction>`;
    }

    function setOutputWrapping(textarea, wrapsText) {
        textarea.wrap = wrapsText ? "soft" : "off";
        textarea.classList.toggle("no-wrap", !wrapsText);
    }

    function showOutput(format, content) {
        const panels = document.getElementById("output-panels");
        const wrapsText = document.getElementById("wrap-output").checked;
        let textarea = document.getElementById(`${format}-output`);
        if (!textarea) {
            const panel = document.createElement("fieldset");
            const legend = document.createElement("legend");
            const label = document.createElement("label");
            textarea = document.createElement("textarea");
            legend.textContent = `${format.toUpperCase()} Output`;
            label.htmlFor = `${format}-output`;
            label.textContent = `Generated ${format.toUpperCase()} code`;
            textarea.id = `${format}-output`;
            textarea.rows = 16;
            textarea.readOnly = true;
            panel.append(legend, label, textarea);
            panels.append(panel);
        }
        setOutputWrapping(textarea, wrapsText);
        textarea.value = content;
    }

    function clearOutputs() {
        document.getElementById("output-panels").replaceChildren();
    }

    function readImageAsDataURL(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.addEventListener("load", () => resolve(reader.result), { once: true });
            reader.addEventListener("error", () => reject(reader.error), { once: true });
            reader.readAsDataURL(file);
        });
    }

    function loadDefaultImage() {
        return fetch(DEFAULT_IMAGE)
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Unable to load the default introduction picture.");
                }
                return response.blob();
            })
            .then(readImageAsDataURL)
            .then((dataURL) => {
                defaultImageData = dataURL;
                const imageSource = document.getElementById("image-source");
                if (imageSource.value === DEFAULT_IMAGE && !document.getElementById("picture-upload").files.length) {
                    imageSource.value = dataURL;
                    document.getElementById("image-preview").src = dataURL;
                }
            })
            .catch(() => {
                defaultImageData = "";
            });
    }

    function resetImagePreview() {
        imageReadToken += 1;
        imageReadPromise = Promise.resolve();
        uploadedImageData = "";
        document.getElementById("picture-upload").value = "";
        document.getElementById("picture-upload").setCustomValidity("");
        document.getElementById("image-source").value = defaultImageData || DEFAULT_IMAGE;
        document.getElementById("image-preview").src = defaultImageData || DEFAULT_IMAGE;
        document.getElementById("image-preview").alt = getValue("pictureAlt");
    }

    function initialize() {
        const form = document.getElementById("introduction-form");
        const courseList = document.getElementById("course-list");
        const pictureUpload = document.getElementById("picture-upload");
        const imagePreview = document.getElementById("image-preview");
        defaultImagePromise = loadDefaultImage();
        DEFAULT_COURSES.forEach((course) => addCourse(course));

        document.getElementById("add-course").addEventListener("click", () => addCourse());
        courseList.addEventListener("click", (event) => {
            const deleteButton = event.target.closest("[data-remove-course]");
            if (deleteButton) {
                deleteButton.closest("[data-course-row]").remove();
                updateCourseLegends();
            }
        });

        pictureUpload.addEventListener("change", () => {
            const file = pictureUpload.files[0];
            const readToken = ++imageReadToken;
            if (!file) {
                uploadedImageData = "";
                imageReadPromise = Promise.resolve();
                pictureUpload.setCustomValidity("");
                document.getElementById("image-source").value = defaultImageData || DEFAULT_IMAGE;
                imagePreview.src = defaultImageData || DEFAULT_IMAGE;
                return;
            }
            if (!file.type.startsWith("image/")) {
                pictureUpload.setCustomValidity("Choose an image file.");
                pictureUpload.reportValidity();
                pictureUpload.setCustomValidity("");
                pictureUpload.value = "";
                uploadedImageData = "";
                imageReadPromise = Promise.resolve();
                document.getElementById("image-source").value = defaultImageData || DEFAULT_IMAGE;
                imagePreview.src = defaultImageData || DEFAULT_IMAGE;
                return;
            }
            pictureUpload.setCustomValidity("");
            imageReadPromise = readImageAsDataURL(file).then((dataURL) => {
                if (readToken === imageReadToken) {
                    uploadedImageData = dataURL;
                    imagePreview.src = dataURL;
                }
            }).catch(() => {
                if (readToken === imageReadToken) {
                    uploadedImageData = "";
                    imagePreview.src = defaultImageData || DEFAULT_IMAGE;
                }
            });
        });

        document.getElementById("picture-alt").addEventListener("input", (event) => {
            imagePreview.alt = event.currentTarget.value;
        });

        document.getElementById("image-source").addEventListener("input", (event) => {
            if (!uploadedImageData) {
                imagePreview.src = event.currentTarget.value || DEFAULT_IMAGE;
            }
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!form.reportValidity()) {
                return;
            }

            await Promise.all([defaultImagePromise, imageReadPromise]);
            const data = readData();
            document.getElementById("generated-introduction").innerHTML = renderIntroduction(data);
            document.getElementById("generated-introduction").hidden = false;
            document.getElementById("generated-footer").innerHTML = renderFooter(data);
            document.getElementById("generated-footer").hidden = false;
            document.getElementById("default-footer").hidden = true;
            document.getElementById("start-over").hidden = false;
            form.hidden = true;
            document.getElementById("generator-controls").hidden = true;
        });

        form.addEventListener("reset", () => {
            window.setTimeout(() => {
                courseList.replaceChildren();
                courseNumber = 0;
                DEFAULT_COURSES.forEach((course) => addCourse(course));
                resetImagePreview();
                clearOutputs();
            });
        });

        document.getElementById("clear-form").addEventListener("click", () => {
            form.querySelectorAll("input:not([type='file']), textarea").forEach((field) => {
                field.value = "";
            });
            pictureUpload.value = "";
            pictureUpload.setCustomValidity("");
            imageReadToken += 1;
            imageReadPromise = Promise.resolve();
            uploadedImageData = "";
            imagePreview.removeAttribute("src");
            imagePreview.alt = "";
            clearOutputs();
        });

        document.querySelectorAll("[data-output]").forEach((button) => {
            button.addEventListener("click", async () => {
                const format = button.dataset.output;
                await Promise.all([defaultImagePromise, imageReadPromise]);
                const data = readData();
                if (format === "html") {
                    showOutput("html", renderHTMLDocument(data));
                } else if (format === "json") {
                    showOutput("json", JSON.stringify(data, null, 2));
                } else {
                    showOutput("xml", renderXML(data));
                }
            });
        });

        document.getElementById("wrap-output").addEventListener("change", (event) => {
            document.querySelectorAll("#output-panels textarea").forEach((textarea) => {
                setOutputWrapping(textarea, event.currentTarget.checked);
            });
        });
    }

    document.addEventListener("DOMContentLoaded", initialize);
})();
