# IT Asset Management System

A full-stack, enterprise-grade application for managing corporate IT hardware and software assets. Features role-based access control, realtime audit tracking, comprehensive inventory limits, Branch/Department encapsulation, and a unified React interface.

---

## 🛠 Technology Stack
* **Backend:** Python + FastAPI, SQLAlchemy (SQLite/PostgreSQL compatible), Pydantic
* **Frontend:** React + Vite, Tailwind CSS (v4), Shadcn/UI primitives, TanStack Query, Lucide-React
* **Authentication:** Stateful JWT via cookies/authorization headers

---

## 🚀 Getting Started

Follow these steps to set up the system entirely from scratch on a new machine.

### 1. Backend Setup (FastAPI)

1. **Clone the repository and open the root folder.**
2. **Create a Python Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure your Environment Map**:
   Ensure you have a `.env` file at the root level mirroring this template:
   ```ini
   DATABASE_URL="sqlite:///./it_assets.db"
   SECRET_KEY="super-secret-key-change-me"
   JWT_ALGORITHM="HS256"
   ACCESS_TOKEN_EXPIRE_MINUTES="1440"
   ADMIN_EMAIL="admin@domain.com"
   ADMIN_PASSWORD="StrongPassword123!"
   ```
5. **Initialize Database** (First time only):
   ```bash
   python scripts/setup_db.py
   ```
   *(This script will create the tables and seed your global administrator account).*
6. **Boot the Backend Server**:
   ```bash
   uvicorn app.server.main:app --reload
   ```
   *The API will be live at: http://localhost:8000*


### 2. Frontend Setup (React/Vite)

1. **Open a separate terminal window and navigate into the client folder**:
   ```bash
   cd app/client
   ```
2. **Install Node Dependencies**:
   ```bash
   npm install
   ```
3. **Boot the Frontend Development Server**:
   ```bash
   npm run dev
   ```
   *The React App will be live at: http://localhost:5173* (Vite will automatically proxy `/api/*` and any matching backend request payloads securely over to `localhost:8000`).

---

## 👥 Default Capabilities

You should log in to `http://localhost:5173` using the `.env` `ADMIN_EMAIL` details.

- **Employees Table**: Manage users, specify branch assignments, and assign rigid access levels (`HR`, `MANAGER`, `SUPPORT_TEAM`, `ADMIN`).
- **Inventory/Stock Portal**: Manage master SKUs for laptops, monitors, accessories, and licenses.
- **Ticketing & Requests**: Standard employees can request new devices or replacements; `HR` or `MANAGER` can triage workflows, `SUPPORT_TEAM` handles assignment.
- **Audit/Tracking Trails**: Irreversible ledger displaying who touched what hardware and when, globally restricted based on employee scopes.
