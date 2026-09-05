import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";
import "./App.css";

const API = "http://127.0.0.1:8000";

const EXAMPLES = [
  "Which category generated the most revenue?",
  "Which region sold the most units?",
  "What is the average unit price?",
  "How many customers are there?",
  "How many orders are there?",
  "Show revenue by region",
];

function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);
  const [dataset, setDataset] = useState(null);

  const [profile, setProfile] = useState(null);
  const [dashboard, setDashboard] = useState(null);

  const [uploadError, setUploadError] = useState("");
  const [dashboardLoading, setDashboardLoading] = useState(false);

  const [darkMode, setDarkMode] = useState(() => {
    return (
      localStorage.getItem("querymind-dark-mode") === "true"
    );
  });

  // =========================================================
  // DARK MODE
  // =========================================================

  useEffect(() => {
    document.body.classList.toggle("dark-mode", darkMode);

    localStorage.setItem(
      "querymind-dark-mode",
      String(darkMode)
    );
  }, [darkMode]);

  function toggleDarkMode() {
    setDarkMode((current) => !current);
  }

  // =========================================================
  // LOAD PROFILE
  // =========================================================

  async function loadProfile() {
    try {
      const response = await fetch(
        `${API}/dataset/profile`
      );

      if (!response.ok) {
        return;
      }

      const data = await response.json();

      if (data.success) {
        setProfile(data);
      }
    } catch (error) {
      console.error("Profile error:", error);
    }
  }

  // =========================================================
  // LOAD DASHBOARD
  // =========================================================

  async function loadDashboard() {
    setDashboardLoading(true);

    try {
      const response = await fetch(
        `${API}/dataset/dashboard`
      );

      if (!response.ok) {
        return;
      }

      const data = await response.json();

      if (data.success) {
        setDashboard(data);
      }
    } catch (error) {
      console.error("Dashboard error:", error);
    } finally {
      setDashboardLoading(false);
    }
  }

  // =========================================================
  // LOAD EXISTING DATASET WHEN APP STARTS
  // =========================================================

  useEffect(() => {
    async function startup() {
      try {
        const response = await fetch(
          `${API}/dataset`
        );

        if (!response.ok) {
          return;
        }

        const data = await response.json();

        if (!data.uploaded) {
          return;
        }

        setDataset(data);

        await loadProfile();
        await loadDashboard();
      } catch {
        console.log("No existing dataset found.");
      }
    }

    startup();
  }, []);

  // =========================================================
  // FILE SELECT
  // =========================================================

  function handleFileChange(event) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setSelectedFile(file);
    setUploadError("");
    setResult(null);
  }

  // =========================================================
  // UPLOAD
  // =========================================================

  async function uploadDataset() {
    if (!selectedFile) {
      setUploadError(
        "Please choose a CSV or Excel file first."
      );
      return;
    }

    setUploading(true);
    setUploadError("");
    setResult(null);

    try {
      const formData = new FormData();

      formData.append("file", selectedFile);

      const response = await fetch(
        `${API}/upload-dataset`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(
          data.error || "Dataset upload failed."
        );
      }

      setDataset(data);
      setSelectedFile(null);

      const fileInput =
        document.getElementById("dataset-file");

      if (fileInput) {
        fileInput.value = "";
      }

      await loadProfile();
      await loadDashboard();
    } catch (error) {
      console.error("Upload error:", error);

      setUploadError(
        error.message ||
          "Could not upload dataset."
      );
    } finally {
      setUploading(false);
    }
  }

  // =========================================================
  // REMOVE DATASET
  // =========================================================

  async function clearDataset() {
    try {
      await fetch(`${API}/dataset`, {
        method: "DELETE",
      });
    } catch (error) {
      console.error("Delete error:", error);
    }

    setDataset(null);
    setProfile(null);
    setDashboard(null);
    setResult(null);
    setQuestion("");
    setSelectedFile(null);

    const fileInput =
      document.getElementById("dataset-file");

    if (fileInput) {
      fileInput.value = "";
    }
  }

  // =========================================================
  // ASK QUESTION
  // =========================================================

  async function askQuestion() {
    const trimmed = question.trim();

    if (!trimmed) {
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(
        `${API}/ask`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json",
          },

          body: JSON.stringify({
            question: trimmed,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error ||
            "Backend request failed."
        );
      }

      setResult(data);
    } catch (error) {
      console.error("Ask error:", error);

      setResult({
        error:
          error.message ||
          "Could not connect to backend.",
      });
    } finally {
      setLoading(false);
    }
  }

  // =========================================================
  // EXAMPLE
  // =========================================================

  function handleExample(example) {
    setQuestion(example);
    setResult(null);
  }

  // =========================================================
  // FORMAT NUMBER
  // =========================================================

  function formatNumber(value) {
    if (
      value === null ||
      value === undefined
    ) {
      return "-";
    }

    if (typeof value !== "number") {
      return String(value);
    }

    return new Intl.NumberFormat("en-IN", {
      maximumFractionDigits: 2,
    }).format(value);
  }

  // =========================================================
  // FORMAT HEADER
  // =========================================================

  function formatHeader(value) {
    return String(value)
      .replaceAll("_", " ")
      .replace(
        /\b\w/g,
        (letter) => letter.toUpperCase()
      );
  }

  // =========================================================
  // RESULT DATA
  // =========================================================

  function getResultData() {
    if (!result) {
      return [];
    }

    if (Array.isArray(result.data)) {
      return result.data;
    }

    if (Array.isArray(result.rows)) {
      return result.rows;
    }

    if (Array.isArray(result.result)) {
      return result.result;
    }

    return [];
  }

  // =========================================================
  // RESULT TABLE
  // =========================================================

  function renderTable() {
    const data = getResultData();

    if (data.length === 0) {
      return null;
    }

    const columns = Object.keys(data[0]);

    return (
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>
                  {formatHeader(column)}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {data.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={column}>
                    {formatNumber(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // =========================================================
  // RESULT CHART
  // =========================================================

  function renderChart() {
    const data = getResultData();

    if (data.length === 0) {
      return null;
    }

    const columns = Object.keys(data[0]);

    if (columns.length !== 2) {
      return null;
    }

    const categoryKey = columns[0];
    const valueKey = columns[1];

    if (result.chart_type === "line") {
      return (
        <div className="chart-container">
          <ResponsiveContainer
            width="100%"
            height={400}
          >
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />

              <XAxis
                dataKey={categoryKey}
              />

              <YAxis
                tickFormatter={formatNumber}
              />

              <Tooltip />

              <Line
                type="monotone"
                dataKey={valueKey}
                stroke="#8b5cf6"
                strokeWidth={3}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      );
    }

    if (result.chart_type === "bar") {
      return (
        <div className="chart-container">
          <ResponsiveContainer
            width="100%"
            height={400}
          >
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />

              <XAxis
                dataKey={categoryKey}
                angle={
                  data.length > 5
                    ? -35
                    : 0
                }
                textAnchor={
                  data.length > 5
                    ? "end"
                    : "middle"
                }
                interval={0}
              />

              <YAxis
                tickFormatter={formatNumber}
              />

              <Tooltip />

              <Bar
                dataKey={valueKey}
                fill="#8b5cf6"
                radius={[
                  6,
                  6,
                  0,
                  0,
                ]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      );
    }

    return null;
  }

  // =========================================================
  // PROFILE
  // =========================================================

  function renderProfile() {
    if (!profile) {
      return null;
    }

    const columnsInfo =
      Array.isArray(profile.columns_info)
        ? profile.columns_info
        : [];

    return (
      <section className="profile-card">
        <div className="profile-header">
          <div>
            <span className="section-label">
              DATASET PROFILE
            </span>

            <h2>
              {profile.filename ||
                dataset?.filename ||
                "Dataset"}
            </h2>
          </div>

          <span
            className={
              profile.quality_status ===
              "good"
                ? "quality-badge good"
                : "quality-badge"
            }
          >
            {profile.quality_status ===
            "good"
              ? "✓ Good"
              : "⚠ Review"}
          </span>
        </div>

        <div className="profile-stats">
          <div className="profile-stat">
            <span>Rows</span>

            <strong>
              {formatNumber(
                profile.rows
              )}
            </strong>
          </div>

          <div className="profile-stat">
            <span>Columns</span>

            <strong>
              {formatNumber(
                profile.columns
              )}
            </strong>
          </div>

          <div className="profile-stat">
            <span>Missing Values</span>

            <strong>
              {formatNumber(
                profile.missing_values
              )}
            </strong>
          </div>

          <div className="profile-stat">
            <span>Duplicate Rows</span>

            <strong>
              {formatNumber(
                profile.duplicate_rows
              )}
            </strong>
          </div>
        </div>

        <div className="quality-row">
          <div className="quality-item">
            <span className="quality-icon">
              {profile.missing_values === 0
                ? "✓"
                : "!"}
            </span>

            <div>
              <strong>
                Missing values
              </strong>

              <p>
                {profile.missing_values ===
                0
                  ? "No missing values found"
                  : `${formatNumber(
                      profile.missing_values
                    )} missing values found`}
              </p>
            </div>
          </div>

          <div className="quality-item">
            <span className="quality-icon">
              {profile.duplicate_rows === 0
                ? "✓"
                : "!"}
            </span>

            <div>
              <strong>
                Duplicate rows
              </strong>

              <p>
                {profile.duplicate_rows ===
                0
                  ? "No duplicate rows found"
                  : `${formatNumber(
                      profile.duplicate_rows
                    )} duplicate rows found`}
              </p>
            </div>
          </div>
        </div>

        <div className="columns-section">
          <h3>Column Details</h3>

          <div className="column-list">
            {columnsInfo.map(
              (column, index) => (
                <div
                  className="column-card"
                  key={`${column.name}-${index}`}
                >
                  <div className="column-main">
                    <strong>
                      {column.name}
                    </strong>

                    <span>
                      {column.type}
                    </span>
                  </div>

                  <div className="column-meta">
                    <span>
                      {formatNumber(
                        column.unique_values
                      )}{" "}
                      unique
                    </span>

                    <span>
                      {formatNumber(
                        column.missing_values
                      )}{" "}
                      missing
                    </span>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </section>
    );
  }

  // =========================================================
  // DASHBOARD
  // =========================================================

  function renderDashboard() {
    if (!dashboard) {
      return null;
    }

    const kpis =
      Array.isArray(dashboard.kpis)
        ? dashboard.kpis
        : [];

    const charts =
      Array.isArray(dashboard.charts)
        ? dashboard.charts
        : [];

    return (
      <section className="dashboard-card">
        <div className="dashboard-header">
          <div>
            <span className="section-label">
              AUTOMATIC DASHBOARD
            </span>

            <h2>
              Dataset Insights
            </h2>

            <p>
              QueryMind automatically analyzed
              your dataset.
            </p>
          </div>

          <span className="analytics-badge">
            ✦ AI Analytics
          </span>
        </div>

        {kpis.length > 0 && (
          <div className="dashboard-kpis">
            {kpis.map(
              (kpi, index) => (
                <div
                  className="dashboard-kpi"
                  key={`${kpi.title}-${index}`}
                >
                  <span>
                    {kpi.title}
                  </span>

                  <strong>
                    {formatNumber(
                      kpi.value
                    )}
                  </strong>
                </div>
              )
            )}
          </div>
        )}

        {charts.length > 0 && (
          <div className="dashboard-charts">
            {charts.map(
              (chart, index) => {
                const chartData =
                  Array.isArray(
                    chart.data
                  )
                    ? chart.data
                    : [];

                const type =
                  chart.type === "line"
                    ? "line"
                    : "bar";

                return (
                  <div
                    className="dashboard-chart-card"
                    key={`${chart.title}-${index}`}
                  >
                    <div className="dashboard-chart-header">
                      <h3>
                        {chart.title}
                      </h3>

                      <span>
                        {type}
                      </span>
                    </div>

                    <ResponsiveContainer
                      width="100%"
                      height={260}
                    >
                      {type === "line" ? (
                        <LineChart
                          data={chartData}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                          />

                          <XAxis
                            dataKey="name"
                          />

                          <YAxis
                            tickFormatter={
                              formatNumber
                            }
                          />

                          <Tooltip />

                          <Line
                            type="monotone"
                            dataKey="value"
                            stroke="#8b5cf6"
                            strokeWidth={3}
                            dot={{ r: 3 }}
                          />
                        </LineChart>
                      ) : (
                        <BarChart
                          data={chartData}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                          />

                          <XAxis
                            dataKey="name"
                            angle={
                              chartData.length >
                              5
                                ? -35
                                : 0
                            }
                            textAnchor={
                              chartData.length >
                              5
                                ? "end"
                                : "middle"
                            }
                            interval={0}
                          />

                          <YAxis
                            tickFormatter={
                              formatNumber
                            }
                          />

                          <Tooltip />

                          <Bar
                            dataKey="value"
                            fill="#8b5cf6"
                            radius={[
                              5,
                              5,
                              0,
                              0,
                            ]}
                          />
                        </BarChart>
                      )}
                    </ResponsiveContainer>
                  </div>
                );
              }
            )}
          </div>
        )}
      </section>
    );
  }

  // =========================================================
  // MAIN UI
  // =========================================================

  return (
    <div
      className={
        darkMode
          ? "app dark"
          : "app"
      }
    >
      {/* HEADER */}

      <header>
        <div className="logo">
          Query<span>Mind</span>
        </div>

        <div className="header-actions">
          <div className="status">
            <span></span>
            AI Analytics
          </div>

          <button
            type="button"
            className="theme-button"
            onClick={toggleDarkMode}
          >
            {darkMode
              ? "☀️"
              : "🌙"}
          </button>
        </div>
      </header>

      <main>
        {/* HERO */}

        <section className="hero">
          <div className="hero-badge">
            ✦ AI-powered data analytics
          </div>

          <h1>
            Ask your data
            <br />
            anything.
          </h1>

          <p>
            QueryMind turns natural-language
            questions into insights using AI +
            Exasol.
          </p>
        </section>

        {/* UPLOAD */}

        <section className="upload-card">
          <div className="upload-title">
            <h3>
              📁 Upload your dataset
            </h3>

            <p>
              Upload a CSV or Excel file to
              analyze your own data.
            </p>
          </div>

          {!dataset ? (
            <>
              <div className="upload-controls">
                <label
                  htmlFor="dataset-file"
                  className="file-button"
                >
                  Choose File
                </label>

                <input
                  id="dataset-file"
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={
                    handleFileChange
                  }
                />

                <button
                  type="button"
                  className="upload-button"
                  onClick={
                    uploadDataset
                  }
                  disabled={
                    !selectedFile ||
                    uploading
                  }
                >
                  {uploading
                    ? "Uploading..."
                    : "Upload Dataset"}
                </button>
              </div>

              {selectedFile && (
                <div className="selected-file">
                  📄{" "}
                  {selectedFile.name}
                </div>
              )}

              {uploadError && (
                <div className="upload-error">
                  {uploadError}
                </div>
              )}
            </>
          ) : (
            <div className="dataset-success">
              <div className="dataset-check">
                ✓
              </div>

              <div className="dataset-details">
                <strong>
                  {dataset.filename}
                </strong>

                <span>
                  {formatNumber(
                    dataset.rows
                  )}{" "}
                  rows •{" "}
                  {formatNumber(
                    dataset.columns_count ??
                      dataset.columns
                  )}{" "}
                  columns
                </span>
              </div>

              <div className="dataset-ready">
                Dataset ready
              </div>

              <button
                type="button"
                className="clear-button"
                onClick={
                  clearDataset
                }
              >
                Remove
              </button>
            </div>
          )}
        </section>

        {/* PROFILE */}

        {renderProfile()}

        {/* DASHBOARD LOADING */}

        {dashboardLoading && (
          <div className="dashboard-loading">
            Analyzing your dataset...
          </div>
        )}

        {/* DASHBOARD */}

        {renderDashboard()}

        {/* ASK */}

        <section className="ask-section">
          <div className="question-box">
            <input
              type="text"
              placeholder={
                dataset
                  ? "Ask a question about your dataset..."
                  : "e.g. How many customers are there?"
              }
              value={question}
              onChange={(event) =>
                setQuestion(
                  event.target.value
                )
              }
              onKeyDown={(event) => {
                if (
                  event.key === "Enter"
                ) {
                  askQuestion();
                }
              }}
            />

            <button
              type="button"
              onClick={
                askQuestion
              }
              disabled={
                loading ||
                !question.trim()
              }
            >
              {loading
                ? "Thinking..."
                : "Ask →"}
            </button>
          </div>

          {/* EXAMPLES */}

          <div className="examples">
            <span>
              Try asking:
            </span>

            {EXAMPLES.map(
              (example) => (
                <button
                  type="button"
                  key={example}
                  onClick={() =>
                    handleExample(
                      example
                    )
                  }
                >
                  {example}
                </button>
              )
            )}
          </div>
        </section>

        {/* RESULTS */}

        {result && (
          <section className="results">
            {result.error ? (
              <div className="error">
                <strong>
                  Something went wrong
                </strong>

                <p>
                  {result.error}
                </p>
              </div>
            ) : (
              <>
                {/* RESULT CARD */}

                <div className="answer-card">
                  <div className="result-heading">
                    <div>
                      <span className="section-label">
                        QUERY RESULT
                      </span>

                      <h2>
                        Result
                      </h2>
                    </div>

                    {result.chart_type && (
                      <span className="chart-badge">
                        {result.chart_type}
                      </span>
                    )}
                  </div>

                  {renderChart()}

                  {renderTable()}
                </div>

                {/* INSIGHT */}

                {result.insight && (
                  <div className="insight-card">
                    <div className="insight-icon">
                      💡
                    </div>

                    <div>
                      <h3>
                        Key Insight
                      </h3>

                      <p>
                        {result.insight}
                      </p>
                    </div>
                  </div>
                )}

                {/* SQL */}

                {result.sql && (
                  <div className="query-card">
                    <h3>
                      Generated SQL
                    </h3>

                    <pre>
                      {result.sql}
                    </pre>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {/* FOOTER */}

        <footer>
          <strong>
            QueryMind
          </strong>

          <span>
            AI + Exasol Analytics
          </span>
        </footer>
      </main>
    </div>
  );
}

export default App;