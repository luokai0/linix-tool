# luocron — Cron Job Manager

> Human-readable scheduling, next-run preview, and job management. Beats raw `crontab -e` with a smart CLI — pure Python, zero dependencies.

## Why luocron?

| Feature | `crontab -e` | **luocron** |
|---|---|---|
| Human-readable schedules | ✗ | ✓ |
| Next-run preview | ✗ | ✓ |
| List all jobs | ✗ | ✓ |
| Remove by name | ✗ | ✓ |
| Job labels | ✗ | ✓ |

## Install

```bash
chmod +x luocron.py
sudo ln -s $(pwd)/luocron.py /usr/local/bin/luocron
```

## Usage

```bash
luocron list                                      # show all cron jobs

# Add jobs using natural language or cron syntax
luocron add daily /scripts/backup.sh
luocron add "every 15 minutes" /scripts/sync.sh
luocron add "at 09:00 weekdays" /scripts/report.sh --label "morning report"
luocron add "on monday at 02:30" /scripts/weekly.sh
luocron add "0 2 * * *" /scripts/db_backup.sh    # raw cron works too

# Remove jobs
luocron remove --index 2                          # by number from 'list'
luocron remove --pattern backup                   # by command substring

# Preview
luocron next "every 15 minutes" -n 10            # show next 10 run times
luocron next daily

# Test run
luocron run "/scripts/test.sh arg1"

# Show all schedule presets
luocron presets
```

## Schedule Presets

```
minutely       every minute
hourly         every hour on the hour
daily          midnight every day
weekly         Sunday midnight
monthly        1st of the month
workdays       weekdays at 09:00
weekends       weekends at 10:00
every5min      every 5 minutes
every15min     every 15 minutes
every30min     every 30 minutes
every2h        every 2 hours
```

## License
MIT — luokai
