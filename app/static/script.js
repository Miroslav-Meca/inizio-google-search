"use strict";

const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const searchButton = document.querySelector("#search-button");
const statusBox = document.querySelector("#status");
const resultsSection = document.querySelector("#results-section");
const resultsList = document.querySelector("#results-list");
const resultsSummary = document.querySelector("#results-summary");
let latestResponse = null;

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.classList.toggle("error", isError);
}

function renderResults(data) {
  resultsList.replaceChildren();
  data.results.forEach((result) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.textContent = result.title;
    link.href = result.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const url = document.createElement("p");
    url.className = "result-url";
    url.textContent = result.url;
    const snippet = document.createElement("p");
    snippet.className = "result-snippet";
    snippet.textContent = result.snippet || "Popis není k dispozici.";
    item.append(link, url, snippet);
    resultsList.append(item);
  });
  resultsSummary.textContent = `Dotaz: „${data.query}“ · ${data.results.length} přirozených výsledků`;
  resultsSection.hidden = false;
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

function csvEscape(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    setStatus("Zadejte klíčovou frázi.", true);
    queryInput.focus();
    return;
  }
  searchButton.disabled = true;
  resultsSection.hidden = true;
  setStatus("Vyhledávám přirozené výsledky…");
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Vyhledávání se nezdařilo.");
    latestResponse = data;
    renderResults(data);
    setStatus(data.results.length ? "Vyhledávání dokončeno." : "Pro tento dotaz nebyly nalezeny přirozené výsledky.");
  } catch (error) {
    setStatus(error.message || "Nepodařilo se spojit se službou vyhledávání.", true);
  } finally {
    searchButton.disabled = false;
  }
});

document.querySelector("#download-json").addEventListener("click", () => {
  if (latestResponse) downloadFile("google-organic-results.json", `${JSON.stringify(latestResponse, null, 2)}\n`, "application/json;charset=utf-8");
});

document.querySelector("#download-csv").addEventListener("click", () => {
  if (!latestResponse) return;
  const rows = [["position", "title", "url", "snippet"], ...latestResponse.results.map((r) => [r.position, r.title, r.url, r.snippet])];
  const csv = rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
  downloadFile("google-organic-results.csv", `\ufeff${csv}\r\n`, "text/csv;charset=utf-8");
});
