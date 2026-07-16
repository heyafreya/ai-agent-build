var currentConversationId = null;

// ── Scenario / Pod helpers ──────────────────────────────────────
function getScenario() {
  return document.getElementById("scenario").value;
}
function getFocusPod() {
  return document.getElementById("pod-filter").value || null;
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

// ── Health score badge ─────────────────────────────────────────
function renderHealthScore(text) {
  var match = text.match(/##\s*Overall Health Score:\s*(.+)/i);
  if (!match) return null;
  var score = match[1].trim();
  var cls = "healthy";
  if (/critical/i.test(score)) cls = "critical";
  else if (/degrad/i.test(score)) cls = "warning";
  return '<div class="health-score ' + cls + '">' + score + "</div>";
}

// ── Charts ─────────────────────────────────────────────────────
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
      '<span class="analysis-bar-pct">' + pct + "%</span></div>";
  });
  return html + "</div>";
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
  var html = '<div class="analysis-chart"><div class="analysis-chart-label">Namespace breakdown</div>';
  nsList.forEach(function (ns) {
    var count = ns.critical + ns.warning + ns.healthy;
    html += '<div class="ns-row"><span class="ns-name">' + ns.name + "</span>" +
      '<div class="ns-bar">' +
        '<div class="ns-seg critical" style="width:' + (count > 0 ? Math.round((ns.critical / count) * 100) : 0) + '%"></div>' +
        '<div class="ns-seg warning" style="width:' + (count > 0 ? Math.round((ns.warning / count) * 100) : 0) + '%"></div>' +
        '<div class="ns-seg healthy" style="width:' + (count > 0 ? Math.round((ns.healthy / count) * 100) : 0) + '%"></div>' +
      "</div><span class='ns-count'>" + count + " pods</span></div>";
  });
  return html + "</div>";
}

function buildPodTable(pods) {
  if (!pods || pods.length === 0) return "";
  var html = '<table class="pod-table"><thead><tr><th>Pod</th><th>Namespace</th><th>Status</th><th>Ready</th><th>Restarts</th><th>Severity</th></tr></thead><tbody>';
  pods.forEach(function (p) {
    html += "<tr><td>" + p.name + "</td><td>" + p.namespace + "</td><td>" + p.status + "</td><td>" + p.ready + "</td><td>" + p.restarts + "</td><td><span class='severity-label " + p.severity + "'>" + p.severity + "</span></td></tr>";
  });
  return html + "</tbody></table>";
}

// ── Agent Trace rendering ──────────────────────────────────────
function renderTrace(trace) {
  if (!trace || !trace.steps || trace.steps.length === 0) return "";
  var html = "";
  trace.steps.forEach(function (step) {
    var isError = step.error !== null;
    var actionLabel = step.action;
    if (step.tool_input && step.tool_input.pod_name) {
      actionLabel += " " + step.tool_input.pod_name;
    }
    html += '<div class="trace-step">';
    html += '<div class="trace-step-header">';
    html += '<span class="trace-step-num">Step ' + step.iteration + "</span>";
    html += '<span class="trace-step-action">' + actionLabel + "</span>";
    if (step.latency_ms > 0) {
      html += '<span class="trace-step-latency">' + step.latency_ms + "ms</span>";
    }
    if (step.tokens_in > 0) {
      html += '<span class="trace-step-tokens">' + step.tokens_in + " in / " + step.tokens_out + " out</span>";
    }
    if (isError) {
      html += '<span class="trace-step-error">' + step.error + "</span>";
    }
    html += "</div>";
    // Expandable details
    html += '<div class="trace-step-details" style="display:none">';
    if (step.tool_input) {
      html += '<div class="trace-detail"><strong>Tool input:</strong><pre>' + JSON.stringify(step.tool_input, null, 2) + "</pre></div>";
    }
    if (step.tool_output) {
      var outputPreview = step.tool_output.length > 800 ? step.tool_output.substring(0, 800) + "\n... (truncated)" : step.tool_output;
      html += '<div class="trace-detail"><strong>Tool output:</strong><pre>' + escapeHtml(outputPreview) + "</pre></div>";
    }
    if (step.llm_raw) {
      html += '<div class="trace-detail"><strong>LLM raw response:</strong><pre>' + escapeHtml(step.llm_raw) + "</pre></div>";
    }
    html += "</div></div>";
  });
  return html;
}

function escapeHtml(text) {
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

function toggleTrace() {
  var body = document.getElementById("trace-body");
  var icon = document.getElementById("trace-toggle-icon");
  if (body.style.display === "none") {
    body.style.display = "block";
    icon.innerHTML = "&#9660;";
  } else {
    body.style.display = "none";
    icon.innerHTML = "&#9654;";
  }
}

// ── Live Demo: Analyze ────────────────────────────────────────
function run_analysis() {
  var btn = document.getElementById("analyze-btn");
  var output = document.getElementById("output");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  output.innerHTML = "Running ReAct agent...";
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
      currentConversationId = analyzeData.conversation_id;

      // Split off alert block
      var parts = result.split("--- Alert Thresholds ---");
      var llmText = parts[0].replace(/^\s*FINAL ANSWER\s*:?\s*\n*/i, "");

      // Render badge
      var badge = renderHealthScore(llmText);
      llmText = llmText.replace(/##\s*Overall Health Score:.*\n*/i, "");

      // Count issues
      var issueMatches = llmText.match(/###\s+.*/g);
      var issueCount = issueMatches ? issueMatches.length : 0;
      llmText = llmText.replace(/##\s*Issues Found/i, "## Issues Found (" + issueCount + ")");

      // Filter charts
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

      // Render trace
      var traceSection = document.getElementById("trace-section");
      var traceMeta = document.getElementById("trace-meta");
      var traceBody = document.getElementById("trace-body");
      if (analyzeData.trace) {
        var trace = analyzeData.trace;
        traceSection.style.display = "block";
        traceMeta.textContent = trace.model + " | " + trace.iterations + " iterations | " + trace.total_latency_ms + "ms | " + (trace.total_tokens_in + trace.total_tokens_out) + " tokens";
        traceBody.innerHTML = renderTrace(trace);
        // Make trace steps expandable
        traceBody.querySelectorAll(".trace-step-header").forEach(function (header) {
          header.addEventListener("click", function () {
            var details = this.nextElementSibling;
            details.style.display = details.style.display === "none" ? "block" : "none";
          });
        });
      }

      // Show chat section
      document.getElementById("chat-section").style.display = "block";
      document.getElementById("chat-messages").innerHTML = "";
    })
    .catch(function (err) {
      output.innerHTML = "Error: " + err.message;
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Analyze";
    });
}

// ── Chat follow-up ────────────────────────────────────────────
function sendChat() {
  var input = document.getElementById("chat-input");
  var msg = input.value.trim();
  if (!msg || !currentConversationId) return;
  input.value = "";

  var messagesDiv = document.getElementById("chat-messages");
  messagesDiv.innerHTML += '<div class="chat-msg user">' + escapeHtml(msg) + "</div>";
  messagesDiv.innerHTML += '<div class="chat-msg assistant thinking">Thinking...</div>';
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg, conversation_id: currentConversationId })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var msgs = messagesDiv.querySelectorAll(".chat-msg.thinking");
      var last = msgs[msgs.length - 1];
      if (last) {
        last.className = "chat-msg assistant";
        last.innerHTML = marked.parse(data.response);
      }
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    })
    .catch(function (err) {
      var msgs = messagesDiv.querySelectorAll(".chat-msg.thinking");
      var last = msgs[msgs.length - 1];
      if (last) last.innerHTML = "Error: " + err.message;
    });
}

// ── Model Comparison ──────────────────────────────────────────
function runComparison() {
  var btn = document.getElementById("compare-btn");
  var output = document.getElementById("compare-output");
  btn.disabled = true;
  btn.textContent = "Comparing...";
  output.innerHTML = '<div class="loading">Running same scenario across all models...</div>';

  var scenario = document.getElementById("compare-scenario").value;

  fetch("/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: scenario })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.results || data.results.length === 0) {
        output.innerHTML = "No results returned.";
        return;
      }
      var html = '<div class="compare-grid">';
      data.results.forEach(function (r) {
        var cls = r.error ? "compare-card error" : "compare-card";
        html += '<div class="' + cls + '">';
        html += '<div class="compare-card-header">';
        html += '<span class="compare-model">' + (r.label || r.model) + "</span>";
        if (r.error) {
          html += '<span class="compare-error-badge">Error</span>';
        }
        html += "</div>";
        html += '<div class="compare-metrics">';
        html += '<div class="compare-metric"><span class="metric-label">Latency</span><span class="metric-value">' + r.latency_ms + "ms</span></div>";
        html += '<div class="compare-metric"><span class="metric-label">Tokens</span><span class="metric-value">' + (r.tokens_in + r.tokens_out) + "</span></div>";
        html += '<div class="compare-metric"><span class="metric-label">Issues found</span><span class="metric-value">' + r.issue_count + "</span></div>";
        html += '<div class="compare-metric"><span class="metric-label">Health score</span><span class="metric-value">' + (r.health_score || "N/A") + "</span></div>";
        html += "</div>";
        if (r.error) {
          html += '<div class="compare-error-detail">' + escapeHtml(r.error) + "</div>";
        } else {
          // Show truncated answer with expandable full view
          var answerPreview = r.answer.length > 400 ? r.answer.substring(0, 400) : r.answer;
          html += '<div class="compare-answer">' + marked.parse(answerPreview) + "</div>";
          if (r.answer.length > 400) {
            html += '<button class="compare-expand-btn" onclick="this.previousElementSibling.innerHTML=marked.parse(' + JSON.stringify(r.answer).replace(/"/g, '&quot;') + ');this.remove()">Show full output</button>';
          }
          // Show trace summary
          if (r.trace && r.trace.steps) {
            html += '<div class="compare-trace-summary">' + r.trace.steps.length + " tool calls</div>";
          }
        }
        html += "</div>";
      });
      html += "</div>";
      output.innerHTML = html;
    })
    .catch(function (err) {
      output.innerHTML = "Error: " + err.message;
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Compare Models";
    });
}

// ── Evaluation ────────────────────────────────────────────────
function runEval() {
  var btn = document.getElementById("eval-btn");
  var output = document.getElementById("eval-output");
  btn.disabled = true;
  btn.textContent = "Evaluating...";
  output.innerHTML = '<div class="loading">Running evaluation suite...</div>';

  var model = document.getElementById("eval-model").value || null;

  fetch("/eval", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: model })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var html = '<div class="eval-report">';
      // Summary cards
      html += '<div class="eval-summary">';
      html += '<div class="eval-card"><span class="eval-card-value">' + data.passed + "/" + data.total_cases + '</span><span class="eval-card-label">Passed</span></div>';
      html += '<div class="eval-card"><span class="eval-card-value">' + Math.round(data.avg_severity_accuracy * 100) + '%</span><span class="eval-card-label">Severity Accuracy</span></div>';
      html += '<div class="eval-card"><span class="eval-card-value">' + Math.round(data.avg_root_cause_recall * 100) + '%</span><span class="eval-card-label">Root Cause Recall</span></div>';
      html += '<div class="eval-card"><span class="eval-card-value">' + Math.round(data.avg_fix_relevance * 100) + '%</span><span class="eval-card-label">Fix Relevance</span></div>';
      html += '<div class="eval-card"><span class="eval-card-value">' + Math.round(data.avg_latency_ms) + 'ms</span><span class="eval-card-label">Avg Latency</span></div>';
      html += '<div class="eval-card"><span class="eval-card-value">' + data.model + '</span><span class="eval-card-label">Model</span></div>';
      html += "</div>";
      // Per-case results
      html += '<div class="eval-cases">';
      data.results.forEach(function (r) {
        var cls = r.passed ? "eval-case passed" : "eval-case failed";
        html += '<div class="' + cls + '">';
        html += '<div class="eval-case-header">';
        html += '<span class="eval-case-id">' + r.case_id + "</span>";
        html += '<span class="eval-case-verdict">' + (r.passed ? "PASS" : "FAIL") + "</span>";
        html += "</div>";
        html += '<div class="eval-case-metrics">';
        html += "Severity: " + (r.severity_correct ? "correct" : "wrong") + " | ";
        html += "Root cause: " + Math.round(r.root_cause_recall * 100) + "% | ";
        html += "Fix: " + Math.round(r.fix_relevance * 100) + "% | ";
        html += "Issues: " + Math.round(r.issue_pod_coverage * 100) + "%";
        if (r.hallucinated_pods.length > 0) {
          html += ' | <span class="eval-hallucination">Hallucinated: ' + r.hallucinated_pods.join(", ") + "</span>";
        }
        html += "</div></div>";
      });
      html += "</div></div>";
      output.innerHTML = html;
    })
    .catch(function (err) {
      output.innerHTML = "Error: " + err.message;
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = "Run Evaluation";
    });
}

// ── Load models into eval dropdown ────────────────────────────
function loadModels() {
  fetch("/models")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var sel = document.getElementById("eval-model");
      data.models.forEach(function (m) {
        var opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.label;
        sel.appendChild(opt);
      });
    });
}

// ── Tab switching ─────────────────────────────────────────────
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
    if (name === "eval" && !loaded.eval) {
      loaded.eval = true;
      loadModels();
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
    document.getElementById("trace-section").style.display = "none";
    document.getElementById("chat-section").style.display = "none";
  });
})();
