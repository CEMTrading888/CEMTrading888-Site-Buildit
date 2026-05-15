#!/usr/bin/env python3
"""
deploy_index.py — copies index.html from /tmp/cem_stage/ to web root.
Logs all output to /var/www/cemtrading888/deploy_log.txt for HTTP inspection.
"""
import os, sys, shutil

LOG = '/var/www/cemtrading888/deploy_log.txt'
SRC = '/tmp/cem_stage/index.html'
DST = '/var/www/cemtrading888/index.html'

def log(msg):
    print(msg)
    try:
        with open(LOG, 'a') as f:
            f.write(msg + '\n')
    except Exception:
        pass

try:
    open(LOG, 'w').close()
except Exception:
    pass

log("=== deploy_index.py START ===")
log(f"uid={os.getuid()} cwd={os.getcwd()}")

# Check source
if not os.path.exists(SRC):
    log(f"ERROR: source not found at {SRC}")
    try:
        import glob
        found = glob.glob('/tmp/cem_stage/*') + glob.glob('/tmp/cem_deploy/*')
        log(f"Files in tmp staging: {found}")
    except Exception as e:
        log(f"glob failed: {e}")
    sys.exit(1)

log(f"Source size: {os.path.getsize(SRC)} bytes")

# Check destination writability
if os.path.exists(DST):
    log(f"Dest exists, writable={os.access(DST, os.W_OK)}")
else:
    log("Dest does not exist yet")

# Copy
try:
    shutil.copy2(SRC, DST)
    log(f"COPY OK — {os.path.getsize(DST)} bytes written to {DST}")
except Exception as e:
    log(f"COPY FAILED: {e}")
    sys.exit(1)

# Verify content
try:
    content = open(DST).read()
    broken = content.count("You're in,")
    resize = content.count("resizeChart")
    log(f"Broken apostrophe count: {broken} (0=fixed)")
    log(f"resizeChart occurrences: {resize} (>0=fix present)")
except Exception as e:
    log(f"verify failed: {e}")

log("=== DONE ===")
