function getScenario() {
  var sel = document.getElementById("scenario");
  return sel.options[sel.selectedIndex].value;
}

function getFocusPod() {
  var sel = document.getElementById("pod-filter");
  return sel.value || null;
}

function loadPods() {
  var sel = document.getElementById("pod-filter");
  sel.innerHTML = '<option value="">All pods</option>';
  fetch("/pods?scenario=" + encodeURIComponent(getScenario()))
    .then(function (r) { return r.json(); })
    .then(function (pods) {
      pods.forEach(function (p) {
        var opt = document.createElement("option");
        opt.value = p.name;
        opt.textContent = p.name + " (" + p.namespace + ") — " + p.status;
        sel.appendChild(opt);
      });
    });
}

function renderHealthScore(text) {
  var match = text.match(/##\s*Overall Health Score:\s*(.+)/i);
  if (!match) return null;
  var score = match[1].trim();
  var cls = "healthy";
  if (/critical/i.test(score)) cls = "critical";
  else if (/degrad/i.test(score)) cls = "warning";
  return '<div class="health-score ' + cls + '">' + score + "</div>";
}

function buildSeverityChart(counts) {
  var total = counts.critical + counts.warning + counts.healthy;
  if (total === 0) return "";
  var html = '<div class="analysis-chart"><div class="analysis-chart-label">Severity</div>';
  var items = [
    { n: counts.critical, cls: "critical", label: "critical" },
    { n: counts.warning, cls: "warning", label: "warning" },
    { n: counts.healthy, cls: "healthy", label: "healthy" }
  ];
  items.forEach(function (item) {
    if (item.n === 0) return;
    var pct = Math.round((item.n / total) * 100);
    html += '<div class="analysis-bar-row">' +
      '<span class="analysis-bar-label">' + item.n + " " + item.label + "</span>" +
      '<div class="analysis-bar"><div class="analysis-bar-fill ' + item.cls + '" style="width:' + pct + '%"></div></div>' +
      '<span class="analysis-bar-pct">' + pct + "%</span>" +
    "</div>";
  });
  html += "</div>";
  return html;
}

function buildNsChart(pods) {
  var nsMap = {};
  pods.forEach(function (p) {
    if (!nsMap[p.namespace]) nsMap[p.namespace] = { critical: 0, warning: 0, healthy: 0 };
    nsMap[p.namespace][p.severity]++;
  });
  var nsList = Object.keys(nsMap).map(function (ns) {
    return { name: ns, critical: nsMap[ns].critical, warning: nsMap[ns].warning, healthy: nsMap[ns].healthy };
  });
  nsList.sort(function (a, b) {
    return (b.critical + b.warning + b.healthy) - (a.critical + a.warning + a.healthy);
  });
  var total = pods.length;
  var html = '<div class="analysis-chart"><div class="analysis-chart-label">Namespace breakdown</div>';
  nsList.forEach(function (ns) {
    var count = ns.critical + ns.warning + ns.healthy;
    html += '<div class="ns-row">' +
      '<span class="ns-name">' + ns.name + "</span>" +
      '<div class="ns-bar">' +
        '<div class="ns-seg critical" style="width:' + (count > 0 ? Math.round((ns.critical / count) * 100) : 0) + '%"></div>' +
        '<div class="ns-seg warning" style="width:' + (count > 0 ? Math.round((ns.warning / count) * 100) : 0) + '%"></div>' +
        '<div class="ns-seg healthy" style="width:' + (count > 0 ? Math.round((ns.healthy / count) * 100) : 0) + '%"></div>' +
      "</div>" +
      '<span class="ns-count">' + count + " pods</span>" +
    "</div>";
  });
  html += "</div>";
  return html;
}

function buildPodTable(pods) {
  if (!pods || pods.length === 0) return "";
  var html = '<table class="pod-table"><thead><tr><th>Pod</th><th>Namespace</th><th>Status</th><th>Ready</th><th>Restarts</th><th>Severity</th></tr></thead><tbody>';
  pods.forEach(function (p) {
    html += "<tr>" +
      "<td>" + p.name + "</td>" +
      "<td>" + p.namespace + "</td>" +
      "<td>" + p.status + "</td>" +
      "<td>" + p.ready + "</td>" +
      "<td>" + p.restarts + "</td>" +
      '<td><span class="severity-label ' + p.severity + '">' + p.severity + "</span></td>" +
    "</tr>";
  });
  html += "</tbody></table>";
  return html;
}

function run_analysis() {
  var btn = document.getElementById("analyze-btn");
  var output = document.getElementById("output");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  output.innerHTML = "Running ReAct agent\u2026";
  output.className = "";

  var scenario = getScenario();
  var focusPod = getFocusPod();
  var analyzeUrl = "/analyze?scenario=" + encodeURIComponent(scenario);
  if (focusPod) analyzeUrl += "&pod=" + encodeURIComponent(focusPod);

  Promise.all([
    fetch(analyzeUrl).then(function (r) { return r.json(); }),
    fetch("/health?scenario=" + encodeURIComponent(scenario)).then(function (r) { return r.json(); })
  ])
    .then(function (results) {
      var analyzeData = results[0];
      var healthData = results[1];
      var result = analyzeData.result || "No result";
      var parts = result.split("--- Alert Thresholds ---");
      var llmText = parts[0];

      llmText = llmText.replace(/^\s*FINAL ANSWER\s*:?\s*\n*/i, "");

      var badge = renderHealthScore(llmText);
      llmText = llmText.replace(/##\s*Overall Health Score:.*\n*/i, "");

      // strip Healthy Namespaces section (redundant with charts)
      llmText = llmText.replace(/##\s*Healthy Namespaces[\s\S]*?(?=##|\n*$)/i, "");

      // count issues from ### headings
      var issueMatches = llmText.match(/###\s+.*/g);
      var issueCount = issueMatches ? issueMatches.length : 0;
      llmText = llmText.replace(/##\s*Issues Found/i, "## Issues Found (" + issueCount + ")");

      // Filter charts/pods to focused pod only
      var chartPods = healthData.pods;
      var chartCounts = healthData.counts;
      if (focusPod) {
        chartPods = healthData.pods.filter(function (p) { return p.name === focusPod; });
        chartCounts = { critical: 0, warning: 0, healthy: 0 };
        chartPods.forEach(function (p) { chartCounts[p.severity]++; });
      }

      var chartsHtml = buildSeverityChart(chartCounts) + buildNsChart(chartPods);
      var podTableHtml = buildPodTable(chartPods);
      var llmHtml = marked.parse(llmText);

      var html = "";
      if (badge) html += badge;
      html += chartsHtml;
      html += llmHtml;
      if (parts[1]) {
        var alertText = parts[1]
          .replace(/^Severity:.*\n*/m, "")
          .replace(/^([A-Z]+):$/gm, "## $1");
        html += '<div class="alert-block">' + marked.parse(alertText) + "</div>";
      }
      html += podTableHtml;
      output.innerHTML = html;
      output.className = "has-result";
    })
    .catch(function (err) {
      output.innerHTML = "Error: " + err.message;
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Analyze";
    });
}

// -- Tab switching --
(function () {
  var tabs = document.querySelectorAll(".tab-content");
  var buttons = document.querySelectorAll(".tab-btn");
  var loaded = {};

  function switchTab(name) {
    buttons.forEach(function (b) { b.classList.remove("active"); });
    tabs.forEach(function (t) { t.classList.remove("active"); });
    document.querySelector('[data-tab="' + name + '"]').classList.add("active");
    document.getElementById(name).classList.add("active");

    if (name === "live" && !loaded.live) {
      loaded.live = true;
      loadPods();
    }
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTab(this.getAttribute("data-tab"));
    });
  });

  document.getElementById("scenario").addEventListener("change", function () {
    loadPods();
    var output = document.getElementById("output");
    output.innerHTML = "Click Analyze to run the LLM agent";
    output.className = "";
  });
})();
