# Colour for her logs, so a terminal is a quick look rather than a wall.
#
# Read by core/desktop.py, which pipes `tail -f` through it. It lives in a file
# rather than inline in a template for one reason: the command it belongs to is
# embedded in an AppleScript string, and an awk program full of quotes and
# backslashes going through that escaping is a bug waiting to happen. The path
# is still a CONSTANT derived from this repo's own location - nothing composes
# it from a request, which is the property desktop.py exists to keep.
#
# What is coloured, and why only this much:
#
#   · SEVERITY is the whole point. Red is an error, yellow is a warning, and
#     everything else is dim. Three steps, because the question being asked of
#     a scrolling log is "is anything wrong", and a rainbow answers it worse
#     than three colours do.
#   · A traceback's own lines carry no level. They inherit the colour of the
#     line above, so a stack trace reads as part of the error it belongs to
#     instead of dropping to grey halfway down.
#   · The timestamp and the logger name are dim, always. They are structure.
#
# Hermes writes `2026-08-26 21:48:47,001 LEVEL logger.name: message`. A line
# that does not match that shape is passed through rather than dropped - the
# unparseable line is often the interesting one.

BEGIN {
    R   = "\033[0m"
    DIM = "\033[2m"
    RED = "\033[1;31m"
    YEL = "\033[33m"

    carry = ""

    print DIM "-- " RED "error" DIM " · " YEL "warning" DIM " · info · ctrl-c to stop --" R
    fflush()
}

{
    level = $3

    # `$4 ~ /:$/` is what tells a log line from a line of prose that happens to
    # have a capitalised third word. Fields rather than a regex over the whole
    # line: BSD awk, which is what macOS ships, has no interval expressions.
    if (level ~ /^[A-Z][A-Z]+$/ && $4 ~ /:$/) {
        if (level == "ERROR" || level == "CRITICAL")
            colour = RED
        else if (level == "WARNING")
            colour = YEL
        else
            colour = ""

        carry = colour

        rest = $0
        sub(/^[^ ]+ [^ ]+ [^ ]+ [^ ]+[ ]?/, "", rest)

        stamp = DIM $1 " " $2 R
        tag = (colour == "" ? DIM : colour) sprintf("%-8s", level) R
        name = DIM substr($4, 1, length($4) - 1) R
        body = (colour == "" ? rest : colour rest R)

        print stamp " " tag " " name " " body
    } else {
        print (carry == "" ? DIM $0 R : carry $0 R)
    }

    # tail -f into a pipe is not a tty, so awk buffers. Without this a live log
    # arrives in 4 KB lumps, which is the opposite of watching it.
    fflush()
}
