import json
from typing import List
import hoser
from hoser.stdlib import xargs

"""
Takes in PGN compressed files from lichess and parses them and summarizes them.
"""

def find(path: hoser.String, pattern: hoser.String) -> hoser.Stream:
    files = hoser.exec("find", [hoser.Input("path", path), "-name", hoser.Input("pattern", pattern)])
    return files

def decompress(compressed: hoser.Stream) -> hoser.Stream:
    decomp = hoser.exec("bzip2", ["-d"], stdin=compressed)
    return decomp

def summarize(pgn: hoser.Stream) -> hoser.Stream:
    resultOnly = hoser.exec("grep", ["-F", "Result"], stdin=pgn)
    summarized = hoser.exec("mawk", ["""
/Result/ {
    split($0, a, "-");
    res = substr(a[1], length(a[1]), 1);
    if (res == 1) white++;
    if (res == 0) black++;
    if (res == 2) draw++;
}
END { print white+black+draw, white, black, draw }
"""], stdin=resultOnly)
    return summarized

@hoser.pipe
def summarize_pgn_file(compressed_pgn: hoser.Stream) -> hoser.Stream:
    rawpgn = decompress(compressed_pgn)
    summary = summarize(rawpgn)
    return summary

@hoser.pipe
def summarize_dir(path: hoser.String) -> hoser.Stream:
    pgn_files = find(path, pattern=hoser.string("*.pgn.bz2"))
    results, errs = hoser.run_lines(pgn_files, summarize_pgn_file(hoser.file(name="line")), err=True)
    return hoser.merge(results, stream_names=errs)


if __name__ == "__main__":
    result = summarize_pgn_file(hoser.file("games/lichess_db_standard_rated_2013-01.pgn.bz2"))
    hoser.run(stdout=result)
