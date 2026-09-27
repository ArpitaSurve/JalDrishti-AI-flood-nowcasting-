cd /home/claude/jd
run() { [ -f flood_$1.npz ] && return; python3 run_event.py $1 "$2" > r_$1.log 2>&1 && python3 flood2d.py $1 >> r_$1.log 2>&1; }
( run e2021 "2021-11-11 03:00"; run e2024n "2024-11-30 09:00"; run e2025 "2025-12-01 11:00" ) &
( run e2022 "2022-12-09 15:00"; run e2024o "2024-10-15 22:00" ) &
wait
