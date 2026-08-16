# Local Deployment Guide (Master GYM POC)

This document provides complete, step-by-step instructions for running the frontend and backend of Master GYM locally on your Windows machine.

---

## 1. Prerequisites

Before running the application, make sure you have the following installed:
1. **Python 3.11+** (Anaconda is installed and active in your current environment).
2. **Node.js (v20+)** (Not yet configured in your system PATH).
   * **To install Node.js**: Download and run the LTS installer from [nodejs.org](https://nodejs.org/). This will install `node` and `npm`.

---

## 2. Backend Deployment

The backend server is a FastAPI application running on Uvicorn. We have already deployed this server for you locally on port `8000`.

To start it manually in the future, follow these steps:

1. Open PowerShell or Command Prompt.
2. Navigate to the backend directory:
   ```powershell
   cd c:\Users\Umar\Desktop\GYM\GYM-backend\backend
   ```
3. Ensure your environment variables are configured in a `.env` file (copied to `c:\Users\Umar\Desktop\GYM\GYM-backend\backend\.env`):
   ```env
   JWT_SECRET=<your_jwt_secret>
   GEMINI_API_KEY=<your_gemini_api_key>
   GROQ_API_KEY=<your_groq_api_key_optional>
   DATABASE_URL=sqlite:///gym_coach.db
   ```
4. Run the database seed script to populate demo accounts and data (pre-seeded database `gym_coach.db` has already been copied for you):
   ```powershell
   python -m scripts.seed --admin-email admin@example.com --admin-password "AdminPassword123" --demo
   ```
5. Start the FastAPI application:
   ```powershell
   python -m uvicorn app.main:app --reload --port 8000
   ```
   * The API docs will be available at: `http://127.0.0.1:8000/docs`

---

## 3. Frontend Deployment

The frontend is a React + TS application built using Vite. Since Vite serves typescript components on the fly, it requires Node.js.

Once Node.js is installed on your machine, follow these steps:

1. Open a new PowerShell terminal.
2. Navigate to the frontend directory:
   ```powershell
   cd c:\Users\Umar\Desktop\GYM\GYM-frontend\frontend
   ```
3. Install frontend dependencies:
   ```powershell
   npm install
   ```
4. Start the frontend development server:
   ```powershell
   npm run dev
   ```
5. Open your browser and navigate to:
   * **`http://localhost:5173`**
   * Vite automatically proxies API requests from `/api` to the backend on `http://127.0.0.1:8000`.

---

## 4. Verification

* **Backend Dev URL**: `http://127.0.0.1:8000/docs` (FastAPI Swagger UI)
* **Frontend Dev URL**: `http://localhost:5173`
* **Demo Logins**:
  * **Member**: `member-demo@example.com` / `DemoMember123`
  * **Trainer**: `trainer-demo@example.com` / `DemoTrainer123`
  * **Admin**: `admin-demo@example.com` / `DemoAdmin123`
