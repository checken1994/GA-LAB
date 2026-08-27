' Silent Background Launcher for SCP on Windows (Zero-Window Execution)
' Prevents conhost.exe / cmd.exe / pwsh.exe console window flashes in 24/7 background mode.
Set WshShell = CreateObject("WScript.Shell")
Set args = WScript.Arguments

If args.Count > 0 Then
    cmd = ""
    For i = 0 To args.Count - 1
        arg = args(i)
        If InStr(arg, " ") > 0 Then
            arg = """" & arg & """"
        End If
        If i = 0 Then
            cmd = arg
        Else
            cmd = cmd & " " & arg
        End If
    Next
    ' 0 = SW_HIDE (do not show any window), False = do not wait for exit
    WshShell.Run cmd, 0, False
End If
