# Screen vs. Tmux Guide

When deciding between `screen` and `tmux` for running your Telegram bot scripts in the background, both are incredibly lightweight. However, here is a quick comparison:

## Which is lighter?
Technically, **`screen`** is slightly lighter. It is a very old, mature piece of software (first released in 1987) with a smaller codebase and fewer features, so it consumes a tiny bit less baseline memory.

However, **`tmux`** (Terminal Multiplexer) is the modern standard. Its resource consumption is still absolutely negligible (often under 5MB of RAM), but it offers a far superior user experience, better splitting capabilities, and active development. 

**Recommendation:** For 99% of modern servers, **`tmux` is highly recommended** due to its ease of use. `screen` is best only if you are on an extremely legacy system where every single megabyte matters.

---

## 1. How to install on Ubuntu

Since you are running an Ubuntu Oracle server, installing either of them is done via the `apt` package manager.

### To install `tmux` (Recommended):
```bash
sudo apt update
sudo apt install tmux -y
```

### To install `screen`:
```bash
sudo apt update
sudo apt install screen -y
```

---

## 2. Cheat Sheet for Running Your Bots

Here is exactly how you can use them to run your `telegram_bot.py` or `vision_bot.py` so they stay alive after you close your SSH connection.

### If using Tmux:
1. **Start a new session:**
   ```bash
   tmux new -s main_bot
   ```
2. **Run your bot:**
   ```bash
   python telegram_bot.py
   ```
3. **Detach (leave it running in the background):**
   Press `Ctrl+B`, let go, and then press `D`.
4. **Re-attach later (to view logs or stop it):**
   ```bash
   tmux attach -t main_bot
   ```

### If using Screen:
1. **Start a new session:**
   ```bash
   screen -S main_bot
   ```
2. **Run your bot:**
   ```bash
   python telegram_bot.py
   ```
3. **Detach (leave it running in the background):**
   Press `Ctrl+A`, let go, and then press `D`.
4. **Re-attach later (to view logs or stop it):**
   ```bash
   screen -r main_bot
   ```

---

## Summary
You can repeat the above commands using a different session name (e.g., `tmux new -s vision_bot`) to run both of your bots in separate, safely detached background windows!
