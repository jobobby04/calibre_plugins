// ==UserScript==
// @name         TOB Story Downloader & Copier
// @namespace    https://github.com/jobobby04/calibre_plugins
// @version      1.0
// @description  Add download button to TOB storyboxes and copy metadata to clipboard
// @match        https://overflowingbra.com/*
// @grant        none
// @require      https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js
// ==/UserScript==

(function() {
    'use strict';

    // Utility: pad with leading zero
    function pad(n) {
        return n < 10 ? '0' + n : n;
    }

    // Convert "9th Sep 25" → ISO timestamp (rough, assumes UTC and 00:00 time)
    function parsePublishedDate(dateStr) {
        // Example input: "9th Sep 25"
        let cleaned = dateStr.replace(/(\d+)(st|nd|rd|th)/, '$1'); // remove suffix
        let parts = cleaned.split(' '); // [9, Sep, 25]
        let day = parseInt(parts[0], 10);
        let monthStr = parts[1];
        let year = parseInt(parts[2], 10);

        // Convert short year
        if (year < 100) {
            year += 2000;
        }

        let months = {
            Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
            Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11
        };

        let month = months[monthStr];
        let d = new Date(Date.UTC(year, month, day, 0, 0, 0));
        return d.toISOString();
    }

    // Tag mapping dictionary
    const TAG_MAP = {
        "slow": "Slow Growth",
        "fast": "Fast Growth",
        "instant": "Instant Growth",
        "magic": "Magically Caused",
        "chem": "Chemically Caused",
        "science": "Scientificly Caused",
        "ag": "Ass Growth",
        "bg": "Breast Growth",
        "fa": "Fat Growth",
        "gts": "Giantess",
        "hg": "Hair Growth",
        "lg": "Leg Growth",
        "mg": "Muscle Growth",
        "mm": "Male Muscle Growth",
        "mpg": "Male Penis Growth",
        "multiple": "Multiple Breasts",
        "big": "Realisticly Large",
        "huge": "Unrealistically Huge",
        "wow": "Gigantic",
        "ft": "Female to Male",
        "tg": "Male to Female",
        "aliens": "Alien Participation",
        "ar": "Age Regression",
        "bond": "Bondage",
        "cb": "Clothes Ripping",
        "hyp": "Hypnosis",
        "inc": "Incest",
        "lac": "Lactation",
        "ment": "Mental Changes",
        "nc": "Non-Con",
        "offstage": "Offstage Events",
        "preg": "Pregnancy",
        "rc": "Remote-Controlled",
        "sc": "Self-Controlled",
        "shem": "Shemale",
        "weird": "Weird Transformations",
        "asleep": "While Sleeping"
    };

    // Normalize tags → comma separated, lowercase
    function normalizeTags(tagStr) {
        return tagStr
            .split(/\s+/) // split on whitespace
            .filter(Boolean) // remove empties
            .map(tag => {
                return TAG_MAP[tag.toLowerCase()] || tag; // map or fallback
            })
            .join(', ');
    }

    function getFilenameFromResponse(res, url) {
        // Try Content-Disposition header
        let cd = res.headers.get("content-disposition");
        if (cd) {
            let match = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
            if (match) {
                return decodeURIComponent(match[1]);
            }
        }
        // Fallback: last path segment
        try {
            let u = new URL(url, location.href);
            return u.pathname.split('/').pop() || "downloaded_file";
        } catch {
            return "downloaded_file";
        }
    }

    async function handleDownload(downloadLink) {
        try {
            let res = await fetch(downloadLink);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            let buf = await res.arrayBuffer();

            let contentType = res.headers.get("content-type") || "";
            let isZip = contentType.includes("zip") ||
                        (new Uint8Array(buf, 0, 4).toString() === "80,75,3,4"); // PK header
            let filename = getFilenameFromResponse(res, downloadLink);

            if (isZip) {
                console.log("Detected ZIP, extracting…");
                let zip = await JSZip.loadAsync(buf);
                for (let [name, file] of Object.entries(zip.files)) {
                    if (!file.dir) {
                        let blob = await file.async("blob");
                        let a = document.createElement("a");
                        a.href = URL.createObjectURL(blob);
                        a.download = name;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                    }
                }
            } else {
                console.log("Detected single file, downloading…");
                let blob = new Blob([buf]);
                let a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
            }
        } catch (e) {
            console.error("Download failed:", e);
            alert("Download failed — see console for details.");
        }
    }

    // Loop through all storyboxes
    document.querySelectorAll('.storybox').forEach(box => {
        let author = box.querySelector('.author a')?.textContent.trim() || "Unknown";
        let title = box.querySelector('.storytitle a')?.textContent.trim() || "Untitled";
        let downloadLink = box.querySelector('.storytitle a')?.getAttribute('href') || "#";
        let summary = box.querySelector('.summary')?.innerHTML.trim() || "";
        let tagsRaw = box.querySelector('.storycodes')?.textContent.trim() || "";
        let tags = normalizeTags(tagsRaw);
        let pubDate = box.querySelector('.submitdate')?.textContent.trim() || "";

        let isoPub = pubDate ? parsePublishedDate(pubDate) : "";
        let nowIso = new Date().toISOString();

        // Build JSON object
        let metadata = {
            title: title,
            authors: [author],
            publisher: "The Overflowing Bra",
            tags: tags,
            pubdate: isoPub,
            comments: summary
        };

        let jsonStr = JSON.stringify(metadata, null, 2);

        // Create button
        const btn = document.createElement("button");
        btn.textContent = "Download Book";
        btn.style.marginLeft = "10px";
        btn.style.padding = "2px 6px";

        btn.addEventListener('click', async () => {
            try {
                // Copy metadata
                await navigator.clipboard.writeText(jsonStr);
                console.log("Metadata copied to clipboard");

                // Trigger download
                await handleDownload(downloadLink);
                //let a = document.createElement('a');
                //a.href = downloadLink;
                //a.download = "";
                //a.click();
            } catch (err) {
                console.error("Clipboard write failed:", err);
                alert("Failed to copy metadata (check browser permissions).");
            }
        });

        // Insert button
        box.querySelector(".storytitle").appendChild(btn);

         const btn2 = document.createElement("button");
        btn2.textContent = "Copy Info";
        btn2.style.marginLeft = "10px";
        btn2.style.padding = "2px 6px";

        btn2.addEventListener('click', async () => {
            try {
                // Copy metadata
                await navigator.clipboard.writeText(jsonStr);
                console.log("Metadata copied to clipboard");
            } catch (err) {
                console.error("Clipboard write failed:", err);
                alert("Failed to copy metadata (check browser permissions).");
            }
        });

        // Insert button
        box.querySelector(".storytitle").appendChild(btn2);
    });
})();