from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

import pyexasol
import pandas as pd
import duckdb

from io import BytesIO
import json
import re

from ollama import chat


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="QueryMind API",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DEFAULT EXASOL CONNECTION
# ============================================================

DEFAULT_CONNECTION = {
    "host": "localhost",
    "port": 9563,
    "user": "sys",
    "password": "exasol",
    "schema": "QUERYMIND",
}

active_connection = DEFAULT_CONNECTION.copy()


# ============================================================
# UPLOADED DATASET
# ============================================================

uploaded_dataset = None
uploaded_filename = None


# ============================================================
# REQUEST MODELS
# ============================================================

class DatabaseConnection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: str
    port: int = 9563
    user: str
    password: str

    # Avoids the Pydantic "schema shadows BaseModel" warning.
    # API still accepts JSON field: "schema"
    db_schema: str = Field(
        default="QUERYMIND",
        alias="schema",
    )


class Question(BaseModel):
    question: str


# ============================================================
# EXASOL CONNECTION
# ============================================================

def get_connection():

    config = active_connection

    dsn = (
        f"{config['host']}"
        f"/nocertcheck:{config['port']}"
    )

    return pyexasol.connect(
        dsn=dsn,
        user=config["user"],
        password=config["password"],
        schema=config["schema"],
        encryption=True,
    )


# ============================================================
# EXASOL SCHEMA
# ============================================================

def get_exasol_schema():

    connection = get_connection()

    schema_name = (
        active_connection["schema"]
        .upper()
        .replace("'", "''")
    )

    query = f"""
        SELECT
            COLUMN_NAME,
            COLUMN_TYPE,
            TABLE_NAME,
            COLUMN_ORDINAL_POSITION
        FROM EXA_ALL_COLUMNS
        WHERE COLUMN_SCHEMA = '{schema_name}'
        ORDER BY
            TABLE_NAME,
            COLUMN_ORDINAL_POSITION
    """

    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    return [
        {
            "column": row[0],
            "type": row[1],
            "table": row[2],
        }
        for row in rows
    ]


# ============================================================
# EXASOL TABLES
# ============================================================

def get_exasol_tables():

    connection = get_connection()

    schema_name = (
        active_connection["schema"]
        .upper()
        .replace("'", "''")
    )

    query = f"""
        SELECT TABLE_NAME
        FROM EXA_ALL_TABLES
        WHERE TABLE_SCHEMA = '{schema_name}'
        ORDER BY TABLE_NAME
    """

    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    return [row[0] for row in rows]


# ============================================================
# UPLOADED DATASET SCHEMA
# ============================================================

def get_uploaded_schema():

    if uploaded_dataset is None:
        return []

    return [
        {
            "column": str(column),
            "type": str(uploaded_dataset[column].dtype),
            "table": "uploaded_data",
        }
        for column in uploaded_dataset.columns
    ]


# ============================================================
# ACTIVE SCHEMA
# ============================================================

def get_active_schema():

    if uploaded_dataset is not None:
        return get_uploaded_schema()

    return get_exasol_schema()


# ============================================================
# JSON SAFE VALUE
# ============================================================

def make_json_safe(value):

    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def home():

    return {
        "app": "QueryMind",
        "status": "running",
        "dataset_uploaded": uploaded_dataset is not None,
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    try:

        connection = get_connection()

        try:
            result = connection.execute(
                "SELECT 1"
            ).fetchone()
        finally:
            connection.close()

        return {
            "status": "healthy",
            "exasol": result[0] == 1,
            "dataset_uploaded": uploaded_dataset is not None,
        }

    except Exception as error:

        return {
            "status": "degraded",
            "exasol": False,
            "dataset_uploaded": uploaded_dataset is not None,
            "error": str(error),
        }


# ============================================================
# CONNECTION STATUS
# ============================================================

@app.get("/connection")
def connection_status():

    return {
        "connected": True,
        "host": active_connection["host"],
        "port": active_connection["port"],
        "user": active_connection["user"],
        "schema": active_connection["schema"],
    }


# ============================================================
# CONNECT TO EXASOL
# ============================================================

@app.post("/connect")
def connect_database(
    connection_data: DatabaseConnection
):

    global active_connection

    try:

        dsn = (
            f"{connection_data.host}"
            f"/nocertcheck:{connection_data.port}"
        )

        connection = pyexasol.connect(
            dsn=dsn,
            user=connection_data.user,
            password=connection_data.password,
            schema=connection_data.db_schema,
            encryption=True,
        )

        try:
            result = connection.execute(
                "SELECT 1"
            ).fetchone()
        finally:
            connection.close()

        if result[0] != 1:

            return {
                "connected": False,
                "error": "Database connection test failed.",
            }

        active_connection = {
            "host": connection_data.host,
            "port": connection_data.port,
            "user": connection_data.user,
            "password": connection_data.password,
            "schema": connection_data.db_schema,
        }

        return {
            "connected": True,
            "message": "Database connected successfully.",
            "host": connection_data.host,
            "port": connection_data.port,
            "schema": connection_data.db_schema,
        }

    except Exception as error:

        return {
            "connected": False,
            "error": str(error),
        }


# ============================================================
# DISCONNECT
# ============================================================

@app.post("/disconnect")
def disconnect_database():

    global active_connection

    active_connection = DEFAULT_CONNECTION.copy()

    return {
        "connected": False,
        "message": "Database connection reset.",
    }


# ============================================================
# SCHEMA
# ============================================================

@app.get("/schema")
def schema():

    try:

        if uploaded_dataset is not None:

            return {
                "database": "UPLOADED_DATASET",
                "table": "uploaded_data",
                "filename": uploaded_filename,
                "columns": get_uploaded_schema(),
            }

        columns = get_exasol_schema()

        return {
            "database": active_connection["schema"],
            "table": f"{active_connection['schema']}.ORDERS",
            "columns": columns,
        }

    except Exception as error:

        return {
            "error": str(error),
            "columns": [],
        }


# ============================================================
# TABLES
# ============================================================

@app.get("/tables")
def tables():

    try:

        if uploaded_dataset is not None:

            return {
                "tables": ["uploaded_data"],
                "count": 1,
            }

        table_list = get_exasol_tables()

        return {
            "tables": table_list,
            "count": len(table_list),
        }

    except Exception as error:

        return {
            "error": str(error),
            "tables": [],
            "count": 0,
        }


# ============================================================
# UPLOAD DATASET
# ============================================================

@app.post("/upload-dataset")
async def upload_dataset(
    file: UploadFile = File(...)
):

    global uploaded_dataset
    global uploaded_filename

    try:

        if not file.filename:

            return {
                "success": False,
                "error": "No file was selected.",
            }

        filename = file.filename.lower()

        allowed_extensions = [
            ".csv",
            ".xlsx",
            ".xls",
        ]

        extension = None

        for allowed in allowed_extensions:

            if filename.endswith(allowed):
                extension = allowed
                break

        if extension is None:

            return {
                "success": False,
                "error": (
                    "Unsupported file type. "
                    "Please upload CSV, XLSX, or XLS."
                ),
            }

        file_bytes = await file.read()

        if not file_bytes:

            return {
                "success": False,
                "error": "The uploaded file is empty.",
            }

        # CSV
        if extension == ".csv":

            try:
                dataframe = pd.read_csv(
                    BytesIO(file_bytes)
                )

            except UnicodeDecodeError:

                dataframe = pd.read_csv(
                    BytesIO(file_bytes),
                    encoding="latin-1",
                )

        # Excel
        else:

            dataframe = pd.read_excel(
                BytesIO(file_bytes)
            )

        # Validate
        if dataframe.empty:

            return {
                "success": False,
                "error": "The uploaded dataset contains no rows.",
            }

        if len(dataframe.columns) == 0:

            return {
                "success": False,
                "error": "The uploaded dataset contains no columns.",
            }

        # Clean column names
        cleaned_columns = []

        for column in dataframe.columns:

            name = str(column).strip()

            if not name:
                name = "column"

            cleaned_columns.append(name)

        dataframe.columns = cleaned_columns

        # Handle duplicate names
        seen = {}
        final_columns = []

        for column in dataframe.columns:

            if column not in seen:

                seen[column] = 0
                final_columns.append(column)

            else:

                seen[column] += 1

                final_columns.append(
                    f"{column}_{seen[column]}"
                )

        dataframe.columns = final_columns

        # Store
        uploaded_dataset = dataframe
        uploaded_filename = file.filename

        columns = [
            {
                "name": str(column),
                "type": str(dataframe[column].dtype),
            }
            for column in dataframe.columns
        ]

        preview = dataframe.head(10)

        preview_data = json.loads(
            preview.to_json(
                orient="records",
                date_format="iso",
            )
        )

        return {
            "success": True,
            "message": "Dataset uploaded successfully.",
            "filename": file.filename,
            "rows": int(len(dataframe)),
            "columns_count": int(len(dataframe.columns)),
            "columns": columns,
            "preview": preview_data,
        }

    except Exception as error:

        print("DATASET UPLOAD ERROR:", error)

        return {
            "success": False,
            "error": str(error),
        }


# ============================================================
# CURRENT DATASET
# ============================================================

@app.get("/dataset")
def get_dataset():

    if uploaded_dataset is None:

        return {
            "uploaded": False,
            "message": "No dataset uploaded.",
        }

    columns = [
        {
            "name": str(column),
            "type": str(uploaded_dataset[column].dtype),
        }
        for column in uploaded_dataset.columns
    ]

    preview = uploaded_dataset.head(10)

    preview_data = json.loads(
        preview.to_json(
            orient="records",
            date_format="iso",
        )
    )

    return {
        "uploaded": True,
        "filename": uploaded_filename,
        "rows": int(len(uploaded_dataset)),
        "columns_count": int(len(uploaded_dataset.columns)),
        "columns": columns,
        "preview": preview_data,
    }


# ============================================================
# DATASET PROFILE
# ============================================================

@app.get("/dataset/profile")
def dataset_profile():

    if uploaded_dataset is None:

        return {
            "success": False,
            "error": "No dataset uploaded.",
        }

    try:

        df = uploaded_dataset

        total_rows = int(len(df))
        total_columns = int(len(df.columns))

        missing_by_column = {}

        for column in df.columns:

            missing_by_column[str(column)] = int(
                df[column].isna().sum()
            )

        total_missing = int(
            sum(missing_by_column.values())
        )

        duplicate_rows = int(
            df.duplicated().sum()
        )

        columns_info = []

        for column in df.columns:

            series = df[column]

            sample_values = [
                make_json_safe(value)
                for value in (
                    series
                    .dropna()
                    .head(5)
                    .tolist()
                )
            ]

            columns_info.append(
                {
                    "name": str(column),
                    "type": str(series.dtype),
                    "unique_values": int(
                        series.nunique(dropna=True)
                    ),
                    "missing_values": int(
                        series.isna().sum()
                    ),
                    "sample_values": sample_values,
                }
            )

        quality_status = (
            "good"
            if total_missing == 0
            and duplicate_rows == 0
            else "warning"
        )

        return {
            "success": True,
            "filename": uploaded_filename,
            "rows": total_rows,
            "columns": total_columns,
            "missing_values": total_missing,
            "duplicate_rows": duplicate_rows,
            "quality_status": quality_status,
            "missing_by_column": missing_by_column,
            "columns_info": columns_info,
        }

    except Exception as error:

        print("DATASET PROFILE ERROR:", error)

        return {
            "success": False,
            "error": str(error),
        }


# ============================================================
# SMART DASHBOARD
# ============================================================

@app.get("/dataset/dashboard")
def dataset_dashboard():

    if uploaded_dataset is None:

        return {
            "success": False,
            "error": "No dataset uploaded.",
        }

    try:

        df = uploaded_dataset.copy()

        dashboard = {
            "success": True,
            "filename": uploaded_filename,
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "kpis": [],
            "charts": [],
            "derived_metrics": {},
        }

        numeric_columns = []
        categorical_columns = []
        date_columns = []

        # ----------------------------------------------------
        # Detect types
        # ----------------------------------------------------

        for column in df.columns:

            series = df[column]
            name_lower = str(column).lower()

            if pd.api.types.is_numeric_dtype(series):

                numeric_columns.append(column)
                continue

            if any(
                word in name_lower
                for word in [
                    "date",
                    "time",
                    "month",
                    "year",
                ]
            ):

                converted = pd.to_datetime(
                    series,
                    errors="coerce",
                )

                if converted.notna().mean() >= 0.70:

                    date_columns.append(column)
                    continue

            converted = pd.to_datetime(
                series,
                errors="coerce",
            )

            if converted.notna().mean() >= 0.90:

                date_columns.append(column)

            else:

                categorical_columns.append(column)

        # ----------------------------------------------------
        # ID detection
        # ----------------------------------------------------

        def is_id_column(column):

            name = str(column).lower()

            id_words = [
                "id",
                "code",
                "postal",
                "postcode",
                "zip",
                "pincode",
                "pin_code",
            ]

            return any(
                word in name
                for word in id_words
            )

        # ----------------------------------------------------
        # Useful category
        # ----------------------------------------------------

        def is_useful_category(column):

            name = str(column).lower()

            bad_words = [
                "id",
                "code",
                "postal",
                "postcode",
                "zip",
                "pincode",
                "pin_code",
                "phone",
                "mobile",
                "email",
                "address",
            ]

            if any(
                word in name
                for word in bad_words
            ):
                return False

            unique_count = int(
                df[column].nunique(dropna=True)
            )

            return 2 <= unique_count <= 15

        # ----------------------------------------------------
        # KPIs
        # ----------------------------------------------------

        dashboard["kpis"].append(
            {
                "title": "Total Rows",
                "value": int(len(df)),
                "type": "number",
            }
        )

        dashboard["kpis"].append(
            {
                "title": "Total Columns",
                "value": int(len(df.columns)),
                "type": "number",
            }
        )

        for column in df.columns:

            if not is_id_column(column):
                continue

            unique_count = int(
                df[column].nunique(dropna=True)
            )

            if unique_count > 0:

                dashboard["kpis"].append(
                    {
                        "title": f"Unique {column}",
                        "value": unique_count,
                        "type": "number",
                    }
                )

                break

        # ----------------------------------------------------
        # Numeric KPIs
        # ----------------------------------------------------

        preferred_numeric = []

        for column in numeric_columns:

            name = str(column).lower()
            score = 0

            if "revenue" in name:
                score += 10
            if "sales" in name:
                score += 9
            if "amount" in name:
                score += 8
            if "price" in name:
                score += 7
            if "cost" in name:
                score += 6
            if "quantity" in name:
                score += 5
            if "units" in name:
                score += 5
            if "age" in name:
                score += 3
            if is_id_column(column):
                score -= 20

            preferred_numeric.append(
                (score, column)
            )

        preferred_numeric.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        for score, column in preferred_numeric:

            if score < -5:
                continue

            series = pd.to_numeric(
                df[column],
                errors="coerce",
            ).dropna()

            if len(series) == 0:
                continue

            dashboard["kpis"].append(
                {
                    "title": f"Average {column}",
                    "value": round(
                        float(series.mean()),
                        2,
                    ),
                    "type": "number",
                }
            )

            if len(dashboard["kpis"]) >= 6:
                break

        # ----------------------------------------------------
        # Category charts
        # ----------------------------------------------------

        useful_categories = []

        for column in categorical_columns:

            if not is_useful_category(column):
                continue

            unique_count = int(
                df[column].nunique(dropna=True)
            )

            name = str(column).lower()
            score = 0

            if "region" in name:
                score += 10
            if "category" in name:
                score += 10
            if "segment" in name:
                score += 10
            if "gender" in name:
                score += 8
            if "country" in name:
                score += 6
            if "state" in name:
                score += 5
            if "city" in name:
                score += 3
            if unique_count <= 10:
                score += 2

            useful_categories.append(
                (score, column)
            )

        useful_categories.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        for score, column in useful_categories[:4]:

            counts = (
                df[column]
                .fillna("Unknown")
                .astype(str)
                .value_counts()
                .head(10)
            )

            chart_data = [
                {
                    "name": str(category),
                    "value": int(count),
                }
                for category, count in counts.items()
            ]

            if chart_data:

                dashboard["charts"].append(
                    {
                        "title": f"{column} Distribution",
                        "type": "bar",
                        "column": str(column),
                        "data": chart_data,
                    }
                )

        # ----------------------------------------------------
        # Numeric charts
        # ----------------------------------------------------

        numeric_candidates = []

        for column in numeric_columns:

            if is_id_column(column):
                continue

            series = pd.to_numeric(
                df[column],
                errors="coerce",
            ).dropna()

            if len(series) < 2:
                continue

            name = str(column).lower()
            score = 0

            if "age" in name:
                score += 10
            if "price" in name:
                score += 8
            if "cost" in name:
                score += 7
            if "quantity" in name:
                score += 6
            if "units" in name:
                score += 6
            if "revenue" in name:
                score += 5
            if "sales" in name:
                score += 5
            if "amount" in name:
                score += 5

            numeric_candidates.append(
                (score, column)
            )

        numeric_candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        for score, column in numeric_candidates[:2]:

            series = pd.to_numeric(
                df[column],
                errors="coerce",
            ).dropna()

            try:

                bucketed = pd.cut(
                    series,
                    bins=10,
                )

                counts = bucketed.value_counts(
                    sort=False
                )

                chart_data = [
                    {
                        "name": str(interval),
                        "value": int(count),
                    }
                    for interval, count
                    in counts.items()
                ]

                if chart_data:

                    dashboard["charts"].append(
                        {
                            "title": f"{column} Distribution",
                            "type": "histogram",
                            "column": str(column),
                            "data": chart_data,
                        }
                    )

            except Exception as error:

                print(
                    "NUMERIC CHART ERROR:",
                    error,
                )

        # ----------------------------------------------------
        # Date charts
        # ----------------------------------------------------

        for column in date_columns[:2]:

            try:

                dates = pd.to_datetime(
                    df[column],
                    errors="coerce",
                ).dropna()

                if len(dates) < 2:
                    continue

                grouped = (
                    dates
                    .dt.to_period("M")
                    .value_counts()
                    .sort_index()
                )

                chart_data = [
                    {
                        "name": str(period),
                        "value": int(count),
                    }
                    for period, count
                    in grouped.items()
                ]

                if chart_data:

                    dashboard["charts"].append(
                        {
                            "title": f"{column} Over Time",
                            "type": "line",
                            "column": str(column),
                            "data": chart_data,
                        }
                    )

            except Exception as error:

                print(
                    "DATE CHART ERROR:",
                    error,
                )

        # ----------------------------------------------------
        # Business columns
        # ----------------------------------------------------

        column_names = {
            str(column).lower(): column
            for column in df.columns
        }

        quantity_column = None
        price_column = None
        revenue_column = None

        for lower_name, original in column_names.items():

            if quantity_column is None and (
                "quantity" in lower_name
                or lower_name == "qty"
                or "units" in lower_name
            ):
                quantity_column = original

            if price_column is None and (
                "unit_price" in lower_name
                or "unit price" in lower_name
                or lower_name == "price"
                or "price" in lower_name
            ):
                price_column = original

            if revenue_column is None and (
                "revenue" in lower_name
                or "sales" in lower_name
                or "amount" in lower_name
            ):
                revenue_column = original

        # ----------------------------------------------------
        # Existing revenue
        # ----------------------------------------------------

        if revenue_column is not None:

            try:

                revenue_series = pd.to_numeric(
                    df[revenue_column],
                    errors="coerce",
                ).dropna()

                if len(revenue_series) > 0:

                    total_revenue = float(
                        revenue_series.sum()
                    )

                    dashboard["kpis"].append(
                        {
                            "title": f"Total {revenue_column}",
                            "value": round(
                                total_revenue,
                                2,
                            ),
                            "type": "number",
                        }
                    )

                    dashboard[
                        "derived_metrics"
                    ]["existing_revenue"] = {
                        "column": str(revenue_column),
                        "total": round(
                            total_revenue,
                            2,
                        ),
                    }

            except Exception as error:

                print(
                    "REVENUE KPI ERROR:",
                    error,
                )

        # ----------------------------------------------------
        # Calculated revenue
        # ----------------------------------------------------

        if (
            quantity_column is not None
            and price_column is not None
        ):

            try:

                quantity = pd.to_numeric(
                    df[quantity_column],
                    errors="coerce",
                )

                price = pd.to_numeric(
                    df[price_column],
                    errors="coerce",
                )

                calculated_revenue = (
                    quantity * price
                )

                valid_revenue = (
                    calculated_revenue.dropna()
                )

                if len(valid_revenue) > 0:

                    total_revenue = float(
                        valid_revenue.sum()
                    )

                    if revenue_column is None:

                        dashboard["kpis"].append(
                            {
                                "title": "Estimated Revenue",
                                "value": round(
                                    total_revenue,
                                    2,
                                ),
                                "type": "currency",
                            }
                        )

                    dashboard[
                        "derived_metrics"
                    ]["calculated_revenue"] = {
                        "formula": (
                            f"{quantity_column} × "
                            f"{price_column}"
                        ),
                        "value": round(
                            total_revenue,
                            2,
                        ),
                    }

            except Exception as error:

                print(
                    "DERIVED REVENUE ERROR:",
                    error,
                )

        # ----------------------------------------------------
        # Remove duplicate KPIs
        # ----------------------------------------------------

        unique_kpis = []
        seen_kpis = set()

        for kpi in dashboard["kpis"]:

            if kpi["title"] in seen_kpis:
                continue

            seen_kpis.add(kpi["title"])
            unique_kpis.append(kpi)

        dashboard["kpis"] = unique_kpis[:7]
        dashboard["charts"] = dashboard["charts"][:6]

        return dashboard

    except Exception as error:

        print(
            "SMART DASHBOARD ERROR:",
            error,
        )

        return {
            "success": False,
            "error": str(error),
        }


# ============================================================
# CLEAR DATASET
# ============================================================

@app.delete("/dataset")
def clear_dataset():

    global uploaded_dataset
    global uploaded_filename

    uploaded_dataset = None
    uploaded_filename = None

    return {
        "success": True,
        "message": "Uploaded dataset cleared.",
    }


# ============================================================
# BUILD SCHEMA TEXT
# ============================================================

def build_schema_text():

    schema_data = get_active_schema()

    if not schema_data:
        return "No columns available."

    lines = []

    for column in schema_data:

        table_name = column.get(
            "table",
            "uploaded_data",
        )

        column_name = column.get(
            "column",
            "",
        )

        column_type = column.get(
            "type",
            "",
        )

        lines.append(
            f"- {table_name}.{column_name}: {column_type}"
        )

    return "\n".join(lines)


# ============================================================
# CLEAN SQL
# ============================================================

def clean_sql(sql):

    if sql is None:
        return ""

    sql = str(sql).strip()

    if sql.startswith("```"):

        lines = sql.splitlines()
        cleaned = []

        for line in lines:

            stripped = line.strip()

            if stripped.startswith("```"):
                continue

            if stripped.lower() == "sql":
                continue

            cleaned.append(line)

        sql = "\n".join(cleaned).strip()

    if sql.lower().startswith("sql\n"):
        sql = sql[4:].strip()

    sql = sql.rstrip(";").strip()

    return sql


# ============================================================
# SQL SAFETY
# ============================================================

def validate_generated_sql(sql):

    sql = clean_sql(sql)

    if not sql:

        return False, "AI returned empty SQL."

    normalized = sql.strip().lower()

    if not (
        normalized.startswith("select")
        or normalized.startswith("with")
    ):

        return False, "Only SELECT queries are allowed."

    if ";" in sql:

        return False, "Multiple SQL statements are not allowed."

    blocked_patterns = [
        r"\binsert\b",
        r"\bupdate\b",
        r"\bdelete\b",
        r"\bdrop\b",
        r"\balter\b",
        r"\bcreate\b",
        r"\btruncate\b",
        r"\bgrant\b",
        r"\brevoke\b",
        r"\bmerge\b",
        r"\breplace\b",
        r"\bcall\b",
        r"\bexecute\b",
    ]

    for pattern in blocked_patterns:

        if re.search(pattern, normalized):

            return False, "Blocked SQL operation."

    return True, sql


# ============================================================
# FORMAT NUMBER
# ============================================================

def format_number(value):

    if value is None:
        return "0"

    if isinstance(value, (int, float)):

        if isinstance(value, float):

            if value.is_integer():
                return f"{int(value):,}"

            return f"{value:,.2f}"

        return f"{value:,}"

    return str(value)


# ============================================================
# NATURAL LANGUAGE INSIGHT
# ============================================================

def generate_insight(data, columns):

    if not data or not columns:
        return None

    # ========================================================
    # ONE COLUMN
    # ========================================================

    if len(columns) == 1:

        column = str(columns[0])
        key = column.lower()

        value = data[0].get(key)
        formatted_value = format_number(value)

        if "count" in key:

            return (
                f"The total count is "
                f"{formatted_value}."
            )

        if (
            "average" in key
            or key.startswith("avg")
        ):

            return (
                f"The average is "
                f"{formatted_value}."
            )

        if (
            "sum" in key
            or "total" in key
        ):

            return (
                f"The total is "
                f"{formatted_value}."
            )

        pretty_column = (
            column
            .replace("_", " ")
            .strip()
        )

        return (
            f"The result is "
            f"{formatted_value} "
            f"for {pretty_column}."
        )

    # ========================================================
    # TWO COLUMNS
    # ========================================================

    if len(columns) == 2:

        category_column = str(columns[0])
        value_column = str(columns[1])

        category_key = category_column.lower()
        value_key = value_column.lower()

        row = data[0]

        category = row.get(category_key)
        value = row.get(value_key)

        formatted_value = format_number(value)

        category_lower = category_column.lower()
        value_lower = value_column.lower()

        # ----------------------------------------------------
        # CUSTOMER COUNT
        # ----------------------------------------------------

        if (
            "customer" in value_lower
            and "count" in value_lower
        ):

            if "region" in category_lower:

                return (
                    f"{category} is the region with "
                    f"the most customers, with "
                    f"{formatted_value} customers."
                )

            if (
                "segment" in category_lower
                or "customer_segment" in category_lower
            ):

                return (
                    f"{category} is the largest customer "
                    f"segment, with {formatted_value} "
                    f"customers."
                )

            if "country" in category_lower:

                return (
                    f"{category} has the most customers, "
                    f"with {formatted_value} customers."
                )

            if "gender" in category_lower:

                return (
                    f"{category} has the highest customer "
                    f"count, with {formatted_value}."
                )

            return (
                f"{category} has the highest customer "
                f"count, with {formatted_value}."
            )

        # ----------------------------------------------------
        # REVENUE
        # ----------------------------------------------------

        if (
            "revenue" in value_lower
            or "sales" in value_lower
        ):

            if "category" in category_lower:

                return (
                    f"{category} generated the highest "
                    f"revenue, at {formatted_value}."
                )

            if "region" in category_lower:

                return (
                    f"{category} generated the highest "
                    f"revenue, at {formatted_value}."
                )

            return (
                f"{category} has the highest revenue, "
                f"at {formatted_value}."
            )

        # ----------------------------------------------------
        # UNITS
        # ----------------------------------------------------

        if (
            "quantity" in value_lower
            or "units" in value_lower
        ):

            if "region" in category_lower:

                return (
                    f"{category} sold the most units, "
                    f"with {formatted_value} units."
                )

            if "category" in category_lower:

                return (
                    f"{category} sold the most units, "
                    f"with {formatted_value} units."
                )

            return (
                f"{category} has the highest unit "
                f"count, with {formatted_value}."
            )

        # ----------------------------------------------------
        # PRICE / COST / AVERAGE
        # ----------------------------------------------------

        if (
            "average" in value_lower
            or value_lower.startswith("avg")
            or "price" in value_lower
            or "cost" in value_lower
        ):

            pretty_value = (
                value_column
                .replace("_", " ")
                .lower()
            )

            return (
                f"{category} has the highest "
                f"{pretty_value}, at "
                f"{formatted_value}."
            )

        # ----------------------------------------------------
        # GENERIC
        # ----------------------------------------------------

        pretty_value = (
            value_column
            .replace("_", " ")
            .lower()
        )

        if len(data) > 1:

            return (
                f"{category} has the highest "
                f"{pretty_value}, with "
                f"{formatted_value}."
            )

        return (
            f"{category} has a value of "
            f"{formatted_value} for "
            f"{pretty_value}."
        )

    # ========================================================
    # MORE THAN TWO COLUMNS
    # ========================================================

    return (
        "The analysis returned "
        f"{len(data)} results across "
        f"{len(columns)} fields."
    )


# ============================================================
# CHART TYPE
# ============================================================

def detect_chart_type(data, columns):

    if not data:
        return "table"

    if len(columns) != 2:
        return "table"

    first_column = str(
        columns[0]
    ).lower()

    second_column = str(
        columns[1]
    ).lower()

    numeric = True

    for row in data:

        value = row.get(
            second_column
        )

        if value is None:
            continue

        if not isinstance(
            value,
            (int, float)
        ):

            numeric = False
            break

    if not numeric:
        return "table"

    if any(
        word in first_column
        for word in [
            "date",
            "time",
            "month",
            "year",
        ]
    ):

        return "line"

    return "bar"


# ============================================================
# ASK
# ============================================================

@app.post("/ask")
def ask(question: Question):

    if not question.question.strip():

        return {
            "error": "Please enter a question."
        }

    try:

        using_uploaded_dataset = (
            uploaded_dataset is not None
        )

        schema_text = build_schema_text()

        # ====================================================
        # UPLOADED DATASET PROMPT
        # ====================================================

        if using_uploaded_dataset:

            prompt = f"""
You are QueryMind, an analytics assistant.

The user uploaded a CSV or Excel dataset.

The dataset table is:

uploaded_data

AVAILABLE COLUMNS:

{schema_text}

Generate ONE SQL query that answers the user's
natural-language question.

IMPORTANT RULES:

- Return ONLY SQL.
- Do not return markdown.
- Do not explain the SQL.
- Only SELECT or WITH queries are allowed.
- Use ONLY uploaded_data.
- Use ONLY the columns listed above.
- Never invent a column.
- Never invent a table.
- Never use INSERT.
- Never use UPDATE.
- Never use DELETE.
- Never use DROP.
- Never use ALTER.
- Never use CREATE.
- Never use TRUNCATE.
- Never use GRANT.
- Never use REVOKE.
- Do not generate multiple statements.

QUERY GUIDELINES:

- "How many" means COUNT(*).
- "How many customers" means COUNT(*) unless
  the question explicitly asks for unique customers.
- "unique customers" means COUNT(DISTINCT customer_id)
  when customer_id exists.
- "total" means SUM(...).
- "average" means AVG(...).
- "highest" means ORDER BY ... DESC LIMIT 1.
- "lowest" means ORDER BY ... ASC LIMIT 1.
- Ranking questions should use ORDER BY DESC.
- Grouped questions should use GROUP BY.
- Return two columns when a chart is useful.

USER QUESTION:

{question.question}
"""

        # ====================================================
        # EXASOL PROMPT
        # ====================================================

        else:

            current_schema = active_connection["schema"]

            prompt = f"""
You are QueryMind, an analytics assistant.

Generate ONE SQL query that answers the user's
natural-language question.

DATABASE:

{current_schema}

AVAILABLE TABLES AND COLUMNS:

{schema_text}

IMPORTANT RULES:

- Return ONLY SQL.
- Do not return markdown.
- Do not explain the SQL.
- Only SELECT or WITH queries are allowed.
- Use ONLY the tables and columns listed above.
- Never invent a table.
- Never invent a column.
- Never use INSERT.
- Never use UPDATE.
- Never use DELETE.
- Never use DROP.
- Never use ALTER.
- Never use CREATE.
- Never use TRUNCATE.
- Never use GRANT.
- Never use REVOKE.
- Do not generate multiple statements.

USER QUESTION:

{question.question}
"""

        # ====================================================
        # OLLAMA
        # ====================================================

        response = chat(
            model="qwen2.5-coder:7b-instruct",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        generated_sql = clean_sql(
            response.message.content
        )

        print()
        print("GENERATED SQL:")
        print(generated_sql)

        # ====================================================
        # SAFETY
        # ====================================================

        valid, validation_result = (
            validate_generated_sql(
                generated_sql
            )
        )

        if not valid:

            return {
                "question": question.question,
                "error": (
                    "Generated SQL failed "
                    "safety validation."
                ),
                "details": validation_result,
                "sql": generated_sql,
            }

        sql = validation_result

        # ====================================================
        # EXECUTE UPLOADED DATASET
        # ====================================================

        if using_uploaded_dataset:

            connection = duckdb.connect(
                database=":memory:"
            )

            try:

                connection.register(
                    "uploaded_data",
                    uploaded_dataset,
                )

                result = connection.execute(sql)

                rows = result.fetchall()

                columns = [
                    description[0]
                    for description
                    in result.description
                ]

            finally:

                connection.close()

        # ====================================================
        # EXECUTE EXASOL
        # ====================================================

        else:

            connection = get_connection()

            try:

                result = connection.execute(sql)

                rows = result.fetchall()

                columns = result.column_names()

            finally:

                connection.close()

        # ====================================================
        # FORMAT DATA
        # ====================================================

        data = []

        for row in rows:

            record = {}

            for index, column in enumerate(columns):

                record[
                    str(column).lower()
                ] = make_json_safe(
                    row[index]
                )

            data.append(record)

        # ====================================================
        # CHART
        # ====================================================

        chart_type = detect_chart_type(
            data,
            columns,
        )

        # ====================================================
        # INSIGHT
        # ====================================================

        insight = generate_insight(
            data,
            columns,
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        return {
            "question": question.question,
            "sql": sql,
            "data": data,
            "chart_type": chart_type,
            "insight": insight,
            "source": (
                "uploaded_dataset"
                if using_uploaded_dataset
                else "exasol"
            ),
            "filename": (
                uploaded_filename
                if using_uploaded_dataset
                else None
            ),
        }

    except Exception as error:

        print()
        print("ASK ERROR:")
        print(error)

        return {
            "question": question.question,
            "error": str(error),
        }


# ============================================================
# REVENUE - EXASOL
# ============================================================

@app.get("/revenue")
def revenue():

    if uploaded_dataset is not None:

        return {
            "error": (
                "Revenue endpoint is for the Exasol "
                "ORDERS dataset. Use /ask for "
                "uploaded datasets."
            )
        }

    try:

        connection = get_connection()

        query = """
            SELECT
                REGION,
                SUM(
                    QUANTITY * UNIT_PRICE
                ) AS REVENUE
            FROM QUERYMIND.ORDERS
            GROUP BY REGION
            ORDER BY REVENUE DESC
        """

        try:

            rows = connection.execute(
                query
            ).fetchall()

        finally:

            connection.close()

        data = [
            {
                "region": region,
                "revenue": float(revenue_value),
            }
            for region, revenue_value in rows
        ]

        return {
            "data": data,
        }

    except Exception as error:

        return {
            "error": str(error),
        }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_message():

    print()
    print("============================================")
    print("        QueryMind Backend Started")
    print("============================================")
    print("CSV upload: ENABLED")
    print("Excel upload: ENABLED")
    print("Dataset profile: ENABLED")
    print("Smart dashboard: ENABLED")
    print("Natural language SQL: ENABLED")
    print("DuckDB uploaded-data engine: ENABLED")
    print("Improved natural-language insights: ENABLED")
    print("============================================")
    print()