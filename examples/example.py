import hoser
import sys

"""
Filters any line containing "cats" or "dogs" from a document

Run using `python examples/example.py <examples/texts/catsdogs.txt`

Equivalent to `grep -v cats | grep -v dogs`

Expected output:

    This is only what should be left

"""

def filter(inp: hoser.Stream, filter: str) -> hoser.Stream:
    return hoser.exec("grep", ["-v", filter], stdin=inp)

@hoser.fn
def add_chickens(n: int):
    for line in sys.stdin:
        print(line + " and chickens!"*n)


filtered = filter(filter(hoser.stdin, "cats"), "dogs")
hoser.stdout = add_chickens(stdin=filtered, n=3)
hoser.run()