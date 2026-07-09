import datetime
def get_gap_hours(time1_str, time2_str):
    # Formato HH:MM
    if not time1_str or not time2_str: return 999
    try:
        t1 = datetime.datetime.strptime(time1_str, "%H:%M")
        t2 = datetime.datetime.strptime(time2_str, "%H:%M")
        diff = (t2 - t1).total_seconds() / 3600.0
        if diff < 0:
            diff += 24.0
        return diff
    except:
        return 999

print(get_gap_hours("20:14", "20:14")) # 0.0
print(get_gap_hours("10:00", "12:00")) # 2.0
print(get_gap_hours("23:00", "01:00")) # 2.0
