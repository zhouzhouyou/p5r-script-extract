using System.Reflection;
using System.Text;

// Batch decompile the FLOW script out of every .BF file, mirroring the input tree.
// Uses FlowScriptDecompiler.TryDecompile(flowScript, filepath), the same entry
// point AtlusScriptCompiler uses, with embedded-message decompilation disabled
// (.msg output is produced separately by the message batch tool).
//
// Usage: flowprobe <inputRoot> <outputRoot> <libraryShortName>

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine("usage: flowprobe <inputRoot> <outputRoot> <library>");
            return 2;
        }

        string inputRoot = Path.GetFullPath(args[0]);
        string outputRoot = Path.GetFullPath(args[1]);
        string libraryName = args[2];
        string toolDir = @"C:\Users\14453\Downloads\Atlus-Script-Tools";

        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        var lib = Assembly.LoadFrom(Path.Combine(toolDir, "AtlusScriptLibrary.dll"));

        var tLookup = lib.GetType("AtlusScriptLibrary.Common.Libraries.LibraryLookup", true);
        tLookup.GetMethod("SetLibraryPath", BindingFlags.Public | BindingFlags.Static)
            .Invoke(null, new object[] { Path.Combine(toolDir, "Libraries") });
        object gameLib = tLookup.GetMethod("GetLibrary", BindingFlags.Public | BindingFlags.Static,
            null, new[] { typeof(string) }, null).Invoke(null, new object[] { libraryName });

        var tEncoding = lib.GetType("AtlusScriptLibrary.Common.Text.Encodings.AtlusEncoding", true);
        tEncoding.GetMethod("SetCharsetDirectory", BindingFlags.Public | BindingFlags.Static)
            .Invoke(null, new object[] { Path.Combine(toolDir, "Charsets") });
        object encoding = tEncoding.GetMethod("Create", BindingFlags.Public | BindingFlags.Static,
            null, new[] { typeof(string) }, null).Invoke(null, new object[] { "P5R_CHS" });

        var tFlowBinary = lib.GetType("AtlusScriptLibrary.FlowScriptLanguage.BinaryModel.FlowScriptBinary", true);
        var tFlowScript = lib.GetType("AtlusScriptLibrary.FlowScriptLanguage.FlowScript", true);
        var tDecompiler = lib.GetType("AtlusScriptLibrary.FlowScriptLanguage.Decompiler.FlowScriptDecompiler", true);

        var mFromStream = tFlowBinary.GetMethod("FromStream", BindingFlags.Public | BindingFlags.Static,
            null, new[] { typeof(Stream), typeof(bool) }, null);
        var mFlowFromBinary = tFlowScript.GetMethods(BindingFlags.Public | BindingFlags.Static)
            .First(m => m.Name == "FromBinary" && m.GetParameters().Length == 2
                        && m.GetParameters()[0].ParameterType == tFlowBinary);
        var mTryDecompile = tDecompiler.GetMethod("TryDecompile", BindingFlags.Public | BindingFlags.Instance,
            null, new[] { tFlowScript, typeof(string) }, null);
        var pLibrary = tDecompiler.GetProperty("Library", BindingFlags.Public | BindingFlags.Instance);
        var pDecompileMessageScript = tDecompiler.GetProperty("DecompileMessageScript", BindingFlags.Public | BindingFlags.Instance);

        if (mTryDecompile == null || mFlowFromBinary == null || mFromStream == null)
        {
            Console.Error.WriteLine("required API not found");
            return 3;
        }

        var files = Directory.EnumerateFiles(inputRoot, "*.bf", SearchOption.AllDirectories)
            .OrderBy(f => f, StringComparer.OrdinalIgnoreCase).ToList();
        Console.WriteLine($"bf files: {files.Count}");

        int ok = 0, empty = 0, fail = 0;
        var failures = new List<string>();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        int processed = 0;

        foreach (var file in files)
        {
            processed++;
            try
            {
                object flowBinary;
                using (var fs = File.OpenRead(file))
                    flowBinary = mFromStream.Invoke(null, new object[] { fs, true });

                object flowScript = mFlowFromBinary.Invoke(null, new[] { flowBinary, encoding });
                if (flowScript == null) { empty++; continue; }

                string rel = Path.GetRelativePath(inputRoot, file);
                string outp = Path.Combine(outputRoot, rel + ".flow");
                Directory.CreateDirectory(Path.GetDirectoryName(outp));

                object dec = Activator.CreateInstance(tDecompiler);
                pLibrary.SetValue(dec, gameLib);
                if (pDecompileMessageScript != null) pDecompileMessageScript.SetValue(dec, false);

                var okFlag = (bool)mTryDecompile.Invoke(dec, new[] { flowScript, outp });
                if (okFlag) ok++; else { fail++; failures.Add(rel + "\treturned false"); }
            }
            catch (Exception ex)
            {
                fail++;
                var inner = ex is TargetInvocationException tie && tie.InnerException != null ? tie.InnerException : ex;
                failures.Add($"{Path.GetRelativePath(inputRoot, file)}\t{inner.GetType().Name}\t{inner.Message}");
            }

            if (processed % 1000 == 0)
                Console.WriteLine($"  {processed}/{files.Count} ok={ok} empty={empty} fail={fail} [{sw.Elapsed.TotalSeconds:F0}s]");
        }

        Console.WriteLine($"DONE ok={ok} empty={empty} fail={fail} in {sw.Elapsed.TotalSeconds:F1}s");
        File.WriteAllLines(Path.Combine(outputRoot, "_flow_failures.tsv"), failures, new UTF8Encoding(false));
        return 0;
    }
}
