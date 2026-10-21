// Browser side of the GUI. Every button sends a request to gui.py (running on this
// computer), which calls the same core functions as the command line and answers
// with JSON. Nothing here touches files directly.
"use strict";

const TOKEN = document.querySelector('meta[name="api-token"]').content;
const $ = (id) => document.getElementById(id);

let selectedVersion = null;     // null = use the latest version
let latestVersion = null;
let versionsCache = [];         // last list from the server, oldest first
let versionPath = null;         // folder of the version shown in "Files in"

// ---------------------------------------------------------------- talking to gui.py

async function api(name, body = {}) {
  let res;
  try {
    res = await fetch(`/api/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Token": TOKEN },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new Error("The backup program isn't running, so this page can't reach it.\n" +
      "Start it again: in Terminal, go to the backup_utility folder and run  python3 gui.py");
  }
  if (res.status === 403) {
    throw new Error("This page belongs to an earlier run of the backup program. Reload the page (Cmd+R).");
  }
  let data;
  try {
    data = await res.json();
  } catch (err) {
    throw new Error(`Unexpected reply from the server (HTTP ${res.status}).`);
  }
  if (!data.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

const folders = () => ({ source: $("source").value, dest: $("dest").value });

// ---------------------------------------------------------------- output box

function addOutput(text, isError = false) {
  const time = new Date().toLocaleTimeString([], { hour12: false });
  // One click can trigger several requests that all fail the same way (e.g. the program is
  // stopped); show that error once. A repeat more than 3 seconds later is a new entry.
  const previous = $("output").lastElementChild;
  if (isError && previous && previous.dataset.text === text && Date.now() - previous.dataset.at < 3000) {
    previous.querySelector(".time").textContent = `[${time}] `;
    return;
  }
  const entry = document.createElement("div");
  entry.className = "entry";
  entry.dataset.text = text;
  entry.dataset.at = Date.now();
  text.split("\n").forEach((line, i) => {
    const row = document.createElement("div");
    if (i === 0) {
      const stamp = document.createElement("span");
      stamp.className = "time";
      stamp.textContent = `[${time}] `;
      row.appendChild(stamp);
    }
    const body = document.createElement("span");
    body.textContent = line || " ";
    const t = line.trim();
    if (isError || t.startsWith("!") || t.startsWith("✘") || t.startsWith("Error")) body.className = "bad";
    else if (t.startsWith("✔")) body.className = "ok";
    row.appendChild(body);
    entry.appendChild(row);
  });
  $("output").appendChild(entry);
  $("output").scrollTop = $("output").scrollHeight;
  entry.scrollIntoView({ block: "nearest", behavior: "smooth" });   // bring the result on screen
}

function setBusy(busy, message) {
  document.querySelectorAll("button.action, button.pick").forEach((b) => (b.disabled = busy));
  $("spinner").hidden = !busy;
  $("status").textContent = message;
}

// Run one action (backup, restore, ...) and show its result. Returns the reply, or null on error.
async function run(label, name, body) {
  setBusy(true, `${label}…`);
  let data = null;
  try {
    data = await api(name, body);
    addOutput(data.text, false);
    setBusy(false, data.problem ? `${label} finished with problems.` : `${label} finished.`);
  } catch (err) {
    addOutput(`Error: ${err.message}`, true);
    setBusy(false, `${label} failed.`);
  }
  await refreshVersions();
  return data;
}

// ---------------------------------------------------------------- versions, log, suggestions

async function refreshVersions() {
  const dest = $("dest").value.trim();
  let versions = [];
  try {
    if (dest) versions = (await api("versions", { dest })).versions;
  } catch (err) {
    addOutput(`Error: ${err.message}`, true);
  }
  versionsCache = versions;
  latestVersion = versions.length ? versions[versions.length - 1].name : null;
  if (!versions.some((v) => v.name === selectedVersion)) selectedVersion = null;

  const tbody = document.querySelector("#versions tbody");
  tbody.replaceChildren();
  versions.forEach((v, i) => {
    const tr = document.createElement("tr");
    tr.dataset.name = v.name;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "version";
    radio.setAttribute("aria-label", `Select version ${v.name}`);
    const cells = [radio, i + 1, v.name, v.mode, v.files, v.size, v.copied, v.linked];
    cells.forEach((value, c) => {
      const td = document.createElement("td");
      if (value instanceof Node) td.appendChild(value);
      else td.textContent = value;
      if (c >= 4) td.className = "num";
      if (c === 2) {
        td.className = "version";
        if (v.name === latestVersion) {
          const tag = document.createElement("span");
          tag.className = "tag";
          tag.textContent = "latest";
          td.appendChild(tag);
        }
      }
      tr.appendChild(td);
    });
    tr.addEventListener("click", () => selectVersion(v.name));
    tbody.appendChild(tr);
  });

  $("no-versions").hidden = versions.length > 0;
  $("version-count").hidden = versions.length === 0;
  $("version-count").textContent = versions.length;
  showSelection();
  await Promise.all([refreshLog(), refreshSuggestions(), refreshFiles(), refreshLab()]);
}

function selectVersion(name) {
  selectedVersion = name === selectedVersion ? null : name;   // click again to unselect
  showSelection();
  refreshSuggestions();
  refreshFiles();
}

function showSelection() {
  document.querySelectorAll("#versions tbody tr").forEach((tr) => {
    const on = tr.dataset.name === selectedVersion;
    tr.classList.toggle("selected", on);
    tr.querySelector("input").checked = on;
  });
  $("restore-version").textContent = selectedVersion || (latestVersion ? `latest (${latestVersion})` : "latest");
  $("btn-use-latest").hidden = selectedVersion === null;
}

// "Files in <version>" table: everything stored in the selected (or latest) version.
async function refreshFiles() {
  const version = selectedVersion || latestVersion;
  const tbody = document.querySelector("#version-files tbody");
  $("files-version").textContent = version ? (selectedVersion ? version : `latest (${version})`) : "no backups yet";
  $("btn-reveal-version").hidden = true;
  let data = null;
  try {
    if (version) data = await api("version_files", { dest: $("dest").value, version });
  } catch (err) { /* shown elsewhere */ }
  tbody.replaceChildren();
  if (!data) return;
  versionPath = data.path;
  $("btn-reveal-version").hidden = !canReveal;
  data.files.forEach((f) => {
    const tr = document.createElement("tr");
    [f.path, f.size, f.stored, f.modified].forEach((value, i) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (i === 1) td.className = "num";
      if (i === 2 && value === "linked") td.className = "linked";
      tr.appendChild(td);
    });
    tr.title = "Click to restore just this file";
    tr.addEventListener("click", () => {
      $("only").value = f.path;
      $("only").focus();
    });
    tbody.appendChild(tr);
  });
}

async function refreshLog() {
  const dest = $("dest").value.trim();
  let lines = [];
  try {
    if (dest) lines = (await api("log", { dest })).lines;
  } catch (err) { /* shown by refreshVersions already */ }
  $("log").textContent = lines.length ? lines.join("\n") : "No log yet. It is created by the first backup.";
  $("log").scrollTop = $("log").scrollHeight;
}

async function refreshSuggestions() {
  const list = $("only-options");
  list.replaceChildren();
  if (!latestVersion) return;
  try {
    const { paths } = await api("files", { dest: $("dest").value, version: selectedVersion });
    paths.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      list.appendChild(opt);
    });
  } catch (err) { /* suggestions are optional */ }
}

// ---------------------------------------------------------------- buttons

$("btn-backup").addEventListener("click", () =>
  run("Backup", "backup", {
    ...folders(),
    keep: $("keep").value,
    full: $("full").checked,
    exclude: $("exclude").value,
  }));

$("btn-status").addEventListener("click", () => run("Change check", "status", folders()));

$("btn-verify").addEventListener("click", () =>
  run("Verify", "verify", { dest: $("dest").value, version: selectedVersion }));

$("btn-restore").addEventListener("click", () => {
  const body = {
    dest: $("dest").value,
    version: selectedVersion,
    target: $("target").value,
    only: $("only").value.replace(/\/+$/, ""),
    overwrite: $("overwrite").checked,
  };
  if (body.overwrite) {
    const where = body.target.trim() || "the original folder";
    const which = selectedVersion || "the latest version";
    if (!confirm(`Files in ${where} that differ from ${which} will be replaced.\n\nContinue?`)) return;
  }
  run("Restore", "restore", body);
});

$("btn-refresh").addEventListener("click", refreshVersions);
$("btn-log").addEventListener("click", refreshLog);
$("btn-use-latest").addEventListener("click", () => selectVersion(null));
$("btn-clear").addEventListener("click", () => $("output").replaceChildren());
$("dest").addEventListener("change", refreshVersions);

// "Choose…" buttons open the native macOS chooser through gui.py.
document.querySelectorAll("button.pick").forEach((button) =>
  button.addEventListener("click", async () => {
    const input = $(button.dataset.pick);
    setBusy(true, "Waiting for you to choose a folder…");
    try {
      let { path, has_other_files: hasOtherFiles } = await api("pick", { start: input.value });
      if (path && input.id === "dest" && hasOtherFiles &&
          confirm(`${path} already has other files in it, so backups would be mixed in with them.\n\n` +
                  `OK: use a new subfolder ${path}/my_backups instead (recommended)\n` +
                  "Cancel: use the folder you picked anyway")) {
        path = `${path}/my_backups`;
      }
      if (path) {
        input.value = path;
        if (input.id === "dest") await refreshVersions();
      }
      setBusy(false, "Ready.");
    } catch (err) {
      addOutput(`Error: ${err.message}`, true);
      setBusy(false, "Ready.");
    }
  }));

// ---------------------------------------------------------------- Test Lab

// Replace a <select>'s options, keeping the current choice if it is still there.
function fillSelect(select, values, labels = {}) {
  const keep = select.value;
  select.replaceChildren();
  if (!values.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "(nothing here yet)";
    select.appendChild(opt);
  }
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = labels[v] || v;
    select.appendChild(opt);
  });
  if (values.includes(keep)) select.value = keep;
}

async function filesIn(version) {
  if (!version) return [];
  try {
    const { paths } = await api("files", { dest: $("dest").value, version });
    return paths.filter((p) => !p.endsWith("/"));
  } catch (err) {
    return [];
  }
}

async function refreshLab() {
  let sourceFiles = [];
  try {
    sourceFiles = (await api("source_files", { source: $("source").value })).files;
  } catch (err) { /* folder missing: leave the list empty */ }
  fillSelect($("lab-source-file"), sourceFiles);

  const names = versionsCache.map((v) => v.name).reverse();     // newest first
  const labels = latestVersion ? { [latestVersion]: `${latestVersion}  (latest)` } : {};
  fillSelect($("lab-version"), names, labels);
  fillSelect($("lab-backup-file"), await filesIn($("lab-version").value));
  fillSelect($("lab-link-file"), await filesIn(latestVersion));
}

$("lab-version").addEventListener("change", async () =>
  fillSelect($("lab-backup-file"), await filesIn($("lab-version").value)));

// One Test Lab button: check the needed choices, optionally confirm, run, then refresh.
function labButton(id, label, name, { body, needs = [], confirmText }) {
  $(id).addEventListener("click", async () => {
    const missing = needs.find((selectId) => !$(selectId).value);
    if (missing) {
      addOutput(`Error: ${label}: choose something in "${document.querySelector(`label[for="${missing}"]`).textContent}" first.`, true);
      return;
    }
    const request = body();
    if (confirmText && !confirm(confirmText(request))) return;
    const data = await run(label, name, request);
    if (data && data.source) {                 // sample data / reset: point the GUI at it
      $("source").value = data.source;
      $("dest").value = data.dest;
      await refreshVersions();
    }
  });
}

const labSource = () => ({ ...folders(), file: $("lab-source-file").value });
const labBackup = () => ({ dest: $("dest").value, version: $("lab-version").value, file: $("lab-backup-file").value });

labButton("lab-edit", "Edit file", "lab_edit", { body: labSource, needs: ["lab-source-file"] });
labButton("lab-delete-source", "Delete file", "lab_delete_source", {
  body: labSource, needs: ["lab-source-file"],
  confirmText: (r) => `Delete ${r.file} from your folder?\n\nIt is in the latest backup, so you can restore it.`,
});
labButton("lab-add", "Add file", "lab_add", { body: folders });
labButton("lab-corrupt", "Corrupt file", "lab_corrupt", {
  body: labBackup, needs: ["lab-version", "lab-backup-file"],
  confirmText: (r) => `Damage ${r.file} inside backup ${r.version} on purpose?\n\n` +
    "Versions that share it through a hard link are damaged too. Run a Full backup afterwards to repair.",
});
labButton("lab-delete-backup", "Delete from backup", "lab_delete_backup", {
  body: labBackup, needs: ["lab-version", "lab-backup-file"],
  confirmText: (r) => `Delete ${r.file} from inside backup ${r.version} on purpose?`,
});
labButton("lab-crash", "Crash simulation", "lab_crash", { body: () => ({ dest: $("dest").value }) });
labButton("lab-attack", "Attack simulation", "lab_attack", {
  body: () => ({ dest: $("dest").value, version: $("lab-version").value }), needs: ["lab-version"],
});
labButton("lab-links", "Hard-link check", "lab_links", {
  body: () => ({ dest: $("dest").value, file: $("lab-link-file").value }), needs: ["lab-link-file"],
});
labButton("lab-sample", "Sample data", "lab_sample", { body: () => ({}) });
labButton("lab-reset", "Demo reset", "lab_reset", {
  body: () => ({}),
  confirmText: () => "Delete the demo folders sample_data/ and my_backups/ next to gui.py and start fresh?",
});

// "Open" / "Show in Finder" buttons
let canReveal = false;
async function reveal(path) {
  try {
    await api("reveal", { path });
  } catch (err) {
    addOutput(`Error: ${err.message}`, true);
  }
}
document.querySelectorAll("button[data-reveal]").forEach((button) =>
  button.addEventListener("click", () => reveal($(button.dataset.reveal).value)));
$("btn-reveal-version").addEventListener("click", () => reveal(versionPath));

// Tabs
document.querySelectorAll(".tabs button").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((t) =>
      t.setAttribute("aria-selected", String(t === tab)));
    document.querySelectorAll(".tab-panel").forEach((panel) =>
      (panel.hidden = panel.id !== `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "log") refreshLog();
    if (tab.dataset.tab === "lab") refreshLab();
  }));

// ---------------------------------------------------------------- start-up

(async function init() {
  try {
    const cfg = await api("config");
    $("source").value = cfg.source;
    $("dest").value = cfg.dest;
    $("keep").value = cfg.keep;
    $("default-excludes").textContent = cfg.default_excludes.join(", ");
    canReveal = cfg.can_pick;
    if (!cfg.can_pick) document.querySelectorAll("button.pick, button.reveal").forEach((b) => (b.hidden = true));
  } catch (err) {
    addOutput(`Error: ${err.message}`, true);
  }
  await refreshVersions();
})();
