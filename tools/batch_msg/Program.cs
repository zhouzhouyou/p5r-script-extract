using System.CodeDom.Compiler;
using System.Reflection;
using System.Text;

// Batch message-script decompiler for Persona 5 Royal (Chinese) script files.
// Uses the Atlus-Script-Tools library (AtlusScriptLibrary.dll) in-process.
//
// Usage: batch <inputRoot> <outputRoot> <charsetName> <libraryShortName>

internal static class Program
{
    private static Assembly _lib;
    private static Type _tAtlusEncoding;
    private static Type _tMessageScript;
    private static Type _tFlowScriptBinary;
    private static Type _tMessageScriptDecompiler;
    private static Type _tLibraryLookup;
    private static Type _tIndentedTextWriter;
    private static Type _tFileTextWriter;
    private static Type _tIMessageScriptBinary;
    private static MethodInfo _mEncodingCreate;
    private static MethodInfo _mMsgFromBinary;
    private static MethodInfo _mMsgFromFile;
    private static MethodInfo _mFlowFromStream;
    private static MethodInfo _mDecompilerDecompile;
    private static ConstructorInfo _cDecompiler;
    private static MethodInfo _mGetLibrary;
    private static PropertyInfo _pLibrary;
    private static PropertyInfo _pOmitUnused;
    private static ConstructorInfo _cIndented;
    private static ConstructorInfo _cFileTextWriter;

    private static readonly List<string> Failures = new();
    private static int _ok, _fail, _noScript, _total;

    private static int Main(string[] args)
    {
        if (args.Length < 4)
        {
            Console.Error.WriteLine("usage: batch <inputRoot> <outputRoot> <charset> <libraryShortName>");
            return 2;
        }

        string inputRoot = Path.GetFullPath(args[0]);
        string outputRoot = Path.GetFullPath(args[1]);
        string charset = args[2];
        string libraryName = args[3];

        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

        string toolDir = @"C:\Users\14453\Downloads\Atlus-Script-Tools";
        _lib = Assembly.LoadFrom(Path.Combine(toolDir, "AtlusScriptLibrary.dll"));
        Console.WriteLine("library: " + _lib.Location);

        _tAtlusEncoding = _lib.GetType("AtlusScriptLibrary.Common.Text.Encodings.AtlusEncoding", true);
        _tMessageScript = _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.MessageScript", true);
        _tFlowScriptBinary = _lib.GetType("AtlusScriptLibrary.FlowScriptLanguage.BinaryModel.FlowScriptBinary", true);
        _tMessageScriptDecompiler = _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.Decompiler.MessageScriptDecompiler", true);
        _tLibraryLookup = _lib.GetType("AtlusScriptLibrary.Common.Libraries.LibraryLookup", true);
        _tIndentedTextWriter = typeof(System.CodeDom.Compiler.IndentedTextWriter);

        var asmSysText = typeof(System.IO.TextWriter).Assembly;
        _tFileTextWriter = _lib.GetType("AtlusScriptLibrary.Common.Text.FileTextWriter", true);

        _tAtlusEncoding.GetMethod("SetCharsetDirectory", BindingFlags.Public | BindingFlags.Static)
            .Invoke(null, new object[] { Path.Combine(toolDir, "Charsets") });
        _mEncodingCreate = _tAtlusEncoding.GetMethod("Create", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(string) }, null);
        object encoding = _mEncodingCreate.Invoke(null, new object[] { charset });
        Console.WriteLine("charset OK: " + charset);

        _mMsgFromBinary = _tMessageScript.GetMethod("FromBinary", BindingFlags.Public | BindingFlags.Static, null,
            new[] { _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.BinaryModel.IMessageScriptBinary", true), _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.FormatVersion", true), typeof(Encoding) }, null);
        _mMsgFromFile = _tMessageScript.GetMethod("FromFile", BindingFlags.Public | BindingFlags.Static, null,
            new[] { typeof(string), _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.FormatVersion", true), typeof(Encoding) }, null);
        _mFlowFromStream = _tFlowScriptBinary.GetMethod("FromStream", BindingFlags.Public | BindingFlags.Static, null,
            new[] { typeof(Stream), typeof(bool) }, null);

        _pLibrary = _tMessageScriptDecompiler.GetProperty("Library", BindingFlags.Public | BindingFlags.Instance);
        _pOmitUnused = _tMessageScriptDecompiler.GetProperty("OmitUnusedFunctions", BindingFlags.Public | BindingFlags.Instance);
        _cDecompiler = _tMessageScriptDecompiler.GetConstructor(new[] { typeof(TextWriter), typeof(TextWriter) });
        if (_cDecompiler == null)
            _cDecompiler = _tMessageScriptDecompiler.GetConstructor(new[] { typeof(TextWriter) });
        _mDecompilerDecompile = _tMessageScriptDecompiler.GetMethod("Decompile", new[] { _tMessageScript });
        _mGetLibrary = _tLibraryLookup.GetMethod("GetLibrary", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(string) }, null);
        _tLibraryLookup.GetMethod("SetLibraryPath", BindingFlags.Public | BindingFlags.Static)
            .Invoke(null, new object[] { Path.Combine(toolDir, "Libraries") });
        object p5rLib = _mGetLibrary.Invoke(null, new object[] { libraryName });
        Console.WriteLine("game library: " + (p5rLib == null ? "NULL" : libraryName));

        var fmtVersion = _lib.GetType("AtlusScriptLibrary.MessageScriptLanguage.FormatVersion", true);
        object detect = Enum.Parse(fmtVersion, "Detect");

        var files = Directory.EnumerateFiles(inputRoot, "*", SearchOption.AllDirectories)
            .Where(f => { var e = Path.GetExtension(f).ToLowerInvariant(); return e is ".bf" or ".bmd" or ".msg"; })
            .OrderBy(f => f, StringComparer.OrdinalIgnoreCase)
            .ToList();
        Console.WriteLine($"candidate files: {files.Count}");

        var sw = System.Diagnostics.Stopwatch.StartNew();
        foreach (var file in files)
        {
            _total++;
            try
            {
                object script = LoadMessageScript(file, detect, encoding);
                if (script == null) { _noScript++; continue; }

                string rel = Path.GetRelativePath(inputRoot, file);
                string outMsg = Path.Combine(outputRoot, rel + ".msg");
                Directory.CreateDirectory(Path.GetDirectoryName(outMsg));

                using (var ftw = new StreamWriter(outMsg, false, new UTF8Encoding(false)))
                using (var writer = new IndentedTextWriter(ftw, "    "))
                {
                    object decompiler = _cDecompiler.GetParameters().Length == 2
                        ? _cDecompiler.Invoke(new object[] { writer, TextWriter.Null })
                        : _cDecompiler.Invoke(new object[] { writer });
                    if (p5rLib != null) _pLibrary.SetValue(decompiler, p5rLib);
                    _pOmitUnused.SetValue(decompiler, true);
                    _mDecompilerDecompile.Invoke(decompiler, new[] { script });
                    writer.Flush();
                }
                WriteHeaderFile(outMsg + ".h", script);
                _ok++;
            }
            catch (Exception ex)
            {
                _fail++;
                var inner = ex is TargetInvocationException tie && tie.InnerException != null ? tie.InnerException : ex;
                Failures.Add($"{Path.GetRelativePath(inputRoot, file)}\t{inner.GetType().Name}\t{inner.Message}");
                if (_fail <= 3)
                {
                    Console.WriteLine("---- FAILURE " + Path.GetRelativePath(inputRoot, file));
                    Console.WriteLine(inner.ToString());
                }
            }

            if (_total % 500 == 0)
                Console.WriteLine($"  {_total}/{files.Count}  ok={_ok} noscript={_noScript} fail={_fail}  [{sw.Elapsed.TotalSeconds:F0}s]");
        }

        sw.Stop();
        Console.WriteLine($"DONE total={_total} ok={_ok} noscript={_noScript} fail={_fail} in {sw.Elapsed.TotalSeconds:F1}s");
        File.WriteAllLines(Path.Combine(outputRoot, "_failures.tsv"), Failures.Select(f => f.Replace('\t', '|')), new UTF8Encoding(false));
        return 0;
    }

    private static readonly System.Text.RegularExpressions.Regex IdentifierRegex =
        new("^[a-zA-Z_][a-zA-Z0-9_]*$", System.Text.RegularExpressions.RegexOptions.Compiled);

    /// <summary>
    /// Writes the ".msg.h" companion that the original tool emits: one "const int NAME = index;"
    /// line per dialog, indented to column 32 like MessageScriptDecompiler does.
    /// </summary>
    private static void WriteHeaderFile(string path, object script)
    {
        var dialogs = (System.Collections.IEnumerable)_tMessageScript
            .GetProperty("Dialogs", BindingFlags.Public | BindingFlags.Instance).GetValue(script);

        var sb = new StringBuilder();
        sb.Append("// Decompiled by Atlus Script Tools").Append(Environment.NewLine);

        int index = 0;
        foreach (var dialog in dialogs)
        {
            string name = (string)dialog.GetType()
                .GetProperty("Name", BindingFlags.Public | BindingFlags.Instance).GetValue(dialog);
            string id = IdentifierRegex.IsMatch(name) ? name : "``" + name + "``";
            sb.Append("const int ").Append(id.PadRight(32)).Append(" = ").Append(index++).Append(';')
              .Append(Environment.NewLine);
        }

        File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
    }

    private static object LoadMessageScript(string file, object detectVersion, object encoding)
    {
        string ext = Path.GetExtension(file).ToLowerInvariant();

        if (ext == ".bf")
        {
            // Primary: flow script containing an embedded message script section.
            try
            {
                using var fs = File.OpenRead(file);
                object flowBinary = _mFlowFromStream.Invoke(null, new object[] { fs, true });
                var section = _tFlowScriptBinary.GetProperty("MessageScriptSection", BindingFlags.Public | BindingFlags.Instance).GetValue(flowBinary);
                if (section != null)
                    return _mMsgFromBinary.Invoke(null, new object[] { section, detectVersion, encoding });
            }
            catch { /* fall through to direct message-script attempt */ }

            // Fallback: some .bf files are plain message scripts.
            try { return _mMsgFromFile.Invoke(null, new object[] { file, detectVersion, encoding }); }
            catch { return null; }
        }

        // .bmd / .msg are plain message scripts.
        return _mMsgFromFile.Invoke(null, new object[] { file, detectVersion, encoding });
    }
}
