# How to run OralSentinel on your computer

This guide assumes you have never set up a programming project before. It
takes about 30 minutes, most of it waiting for downloads. You need a Windows
computer with at least 8 GB of RAM, about 3 GB of free disk space and an
internet connection for the setup.

OralSentinel is a research prototype. It is not a medical device and its
results are not a diagnosis.

## Step 1. Install two programs (once)

**Python 3.14**

1. Go to https://www.python.org/downloads/ and download the latest **3.14**
   release for Windows (look for "Python 3.14.x", then
   "Windows installer (64-bit)"). Do not pick a newer version such as 3.15:
   the app is tested on 3.14.
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"**
   at the bottom, then click "Install Now".

**Node.js**

1. Go to https://nodejs.org/ and download the **LTS** version.
2. Run the installer and accept the default options.

## Step 2. Unzip the project

1. Right-click `OralSentinel-code.zip` and choose **Extract All...**
2. Extract it to a simple location, for example `C:\OralSentinel`.

You should now have a folder that contains `setup.bat`, `start.bat`,
`backend`, `frontend` and `ml`.

## Step 3. Run the setup (once)

Open the extracted folder and **double-click `setup.bat`**.

A black window opens and shows four steps. Step 2 downloads about 1 GB and
can take 10 to 20 minutes. When you see **"Setup finished"**, press any key
to close the window.

If Windows shows "Windows protected your PC", click **More info**, then
**Run anyway**. The file only runs the commands described in this guide.

## Step 4. Start the app (every time)

**Double-click `start.bat`.**

Two black windows open: "OralSentinel backend" and "OralSentinel website".
After about 30 seconds your browser opens **http://localhost:5173**. If it does
not, open that address yourself.

Keep both windows open while you use the app. To stop it, close both windows.

## Step 5. Use it

1. Click **Create one** to make an account (it stays on your computer).
2. Click **New Analysis**, upload a clear close-up photo of the lesion, fill
   in the patient form and tick the consent box.
3. Click **Run analysis**. The result, heatmap and PDF report appear after a
   few seconds.

## The same steps by typing commands

If you prefer the terminal, or the .bat files do not work, open **Command
Prompt** (press the Windows key, type `cmd`, press Enter) and type these
commands one at a time. Replace `C:\OralSentinel` with your folder.

Setup (once):

```
cd /d C:\OralSentinel
py -3.14 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

Then create a text file called `.env` inside the `backend` folder with these
lines (Notepad works; choose "All files" when saving so it is not saved as
`.env.txt`):

```
DATABASE_URL=sqlite:///./oralsentinel.db
AUTO_CREATE_TABLES=true
MODEL_PATH=../ml/artifacts/resnet50_oral_cancer_v7.pt
GATE_MODEL_PATH=../ml/artifacts/oral_photo_gate_v1.pt
GRADING_MODEL_PATH=../ml/artifacts/resnet50_dysplasia_grade_v2.pt
SECRET_KEY=change-this-to-any-long-random-text-of-40-or-more-characters
```

Start (every time), in **two** Command Prompt windows:

Window 1, the backend:

```
cd /d C:\OralSentinel\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Wait until it says `Application startup complete`.

Window 2, the website:

```
cd /d C:\OralSentinel\frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

**Mac or Linux:** the same steps work in Terminal with `python3.14 -m venv
backend/.venv`, `backend/.venv/bin/python` instead of
`backend\.venv\Scripts\python.exe`, and forward slashes in paths. These
systems have not been tested.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python 3.14 was not found" | Install Python 3.14 (Step 1) and tick "Add python.exe to PATH". Then close the window and run `setup.bat` again. |
| "Node.js was not found" or "'npm' is not recognized" | Install Node.js (Step 1), restart the computer, run `setup.bat` again. |
| Setup stops during step 2 with a network error | Check the internet connection and run `setup.bat` again. It continues where it stopped. |
| The website says "Could not reach the server" | The backend window is closed or still loading. Wait 30 seconds, or run `start.bat` again. |
| "address already in use" or "port 8000/5173 is in use" | OralSentinel is already running. Close the old windows first, or restart the computer. |
| A photo is refused | The app only accepts clear clinical photos of the mouth. Retake it closer, in focus and in good light. |

Your accounts and analyses are saved in `backend\oralsentinel.db` and the
uploaded photos in `backend\app\uploads`. Deleting those resets the app.
