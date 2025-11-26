# =====================================================
# CHOP Execute DAT : balls_position_updater
# Purpose:
#   Updates ball positions in metaball.html from DAT Table
#   Reads 'balls_positions_table' and sends to 'webrender1'
#   via window.setAllBallPositions([...])
# =====================================================

# --- CONFIG ---
TABLE_DAT = 'balls_positions_table'
WEB_RENDER = 'webrender1'
MAX_BALLS = 5

# --- CALLBACKS ---
def onValueChange(channel, sampleIndex, val, prev):
    """
    Called when the CHOP channel changes
    Configure to trigger on a CHOP that pulses when the DAT changes
    """
    updateBallsPositions()


def updateBallsPositions():
    """
    Reads the DAT Table and sends positions to Web Render TOP
    """

    # Get the DAT Table
    table = op(TABLE_DAT)

    if not table:
        print(f"ERROR: DAT Table '{TABLE_DAT}' not found!")
        return

    # Get the Web Render TOP
    web = op(WEB_RENDER)

    if not web:
        print(f"ERROR: Web Render TOP '{WEB_RENDER}' not found!")
        return

    # Read positions from DAT Table
    # Expected format:
    # Row 0 (header) : ball_id | x | y
    # Row 1          : 0       | 540 | 135
    # Row 2          : 1       | 925 | 415
    # etc.

    positions = []

    # Iterate through DAT rows (skip header row 0)
    for row in range(1, min(table.numRows, MAX_BALLS + 1)):  # 5 balls max (rows 1-5)
        try:
            x = float(table[row, 1].val)  # Column 1 = x
            y = float(table[row, 2].val)  # Column 2 = y
            positions.append([x, y])
        except:
            print(f"ERROR reading row {row}")
            positions.append([500, 500])  # Default value

    # Build JavaScript
    import json
    positions_json = json.dumps(positions)

    js = f"if(window.setAllBallPositions) window.setAllBallPositions({positions_json});"

    try:
        web.executeJavaScript(js)
        print(f"Positions updated: {len(positions)} balls")
    except Exception as e:
        print(f"ERROR executing JavaScript: {e}")


# --- OTHER REQUIRED CALLBACKS ---
def offToOn(channel, sampleIndex, val, prev):
    pass

def whileOn(channel, sampleIndex, val, prev):
    pass

def onToOff(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass

def afterCook(channel, sampleIndex, val, prev):
    pass
