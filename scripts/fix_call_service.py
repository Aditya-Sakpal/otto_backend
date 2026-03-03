from pathlib import Path

def main():
    p = Path("app/services/call_service.py")
    s = p.read_text(encoding="utf-8")
    idx = s.find("insert_sql = text")
    if idx != -1:
        snippet = s[idx:idx+800]
        print('FOUND insert_sql snippet repr:')
        print(repr(snippet))
    else:
        print('insert_sql not found')
    # debug counts
    # find occurrences of three-character sequence backslash, 'n', '+'
    occ = []
    for i in range(len(s)-2):
        if s[i] == '\\\\' and s[i+1] == 'n' and s[i+2] == '+':
            occ.append(i)
    print('Found backslash-n-plus occurrences:', len(occ))
    if occ:
        print('Sample context repr:', repr(s[occ[0]:occ[0]+20]))
        # replace the sequence with an actual newline
        s2 = s.replace('\\\\n+','\\n')
        p.write_text(s2, encoding='utf-8')
        print('Replaced occurrences')

if __name__ == "__main__":
    main()

