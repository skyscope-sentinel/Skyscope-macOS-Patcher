====================================================
        Legacy Build Scripts – Reference Guide
====================================================

Folder: old_scripts/
File:   README_legacy.txt
Date:   2025-07-17

This document explains WHY the following scripts are kept for reference
only and WHY **skyscope_unified_compiler.sh** is now the single,
supported way to build, package and install Skyscope macOS Patcher.

----------------------------------------------------
1. Why were these scripts deprecated?
----------------------------------------------------
• Fragmentation – each script automated a different stage of the
  tool-chain; users had to guess which one to run in what order.

• Divergent dependency logic – brew vs. pip vs. conda logic differed,
  causing inconsistent environments and frequent package conflicts.

• Repetition – 60-80 % of the code overlapped, inflating maintenance
  cost and duplicating bug-fixes.

• Incomplete error-handling – most legacy scripts aborted silently on
  network errors or missing CLT, leaving half-built artefacts.

• Missing support for macOS 26.x betas – version-spoof patches and
  Metal-bridge kext hooks were only added to the new unified workflow.

The **unified compiler script** consolidates every step (dependency
bootstrap ➜ OCLP patching ➜ GPU bridges ➜ app build ➜ DMG ➜ install) in
one place, with consistent logging and robust fall-backs.

----------------------------------------------------
2. Script-by-script overview
----------------------------------------------------
A. build_and_release.sh
   • Purpose   – CI tool used to bump version numbers and push GitHub
                 releases.
   • Issues    – Hard-coded tokens, no interactive usage, depended on
                 external GH-CLI.
   • Replaced by – “--build” flag + GitHub Action 'release.yml' that
                   calls skyscope_unified_compiler.sh.

B. build_complete_skyscope.sh
   • Purpose   – Monolithic bash script that attempted *everything*
                 including USB creator and notarisation.
   • Issues    – 4 000+ lines, slow, broke under zsh; no Anaconda
                 support; Metal beta patches missing.
   • Replaced by – unified script + usb_creator.py (modular).

C. build_skyscope_oclp.sh
   • Purpose   – Early PoC to automate OpenCore-Legacy-Patcher fork.
   • Issues    – Out-of-date OCLP version, separate GPU patch logic,
                 root-execution bugs, Homebrew-only installs.
   • Replaced by – unified script which embeds latest OCLP (2.4.0+) and
                   adds Sequoia/Tahoe/26.x beta compatibility.

D. install_skyscope.sh
   • Purpose   – Copied built .app & kexts to /Applications and
                 /Library/Extensions.
   • Issues    – Assumed prior build, no privilege checks, skipped kext
                 cache refresh, SIP assumptions.
   • Replaced by – “--install” flag of unified script with sudo
                   elevation and kextcache rebuild.

----------------------------------------------------
3. When might I still look at these scripts?
----------------------------------------------------
• Historical reference – to see how certain flags or release-rules were
  handled in the past.

• Custom CI integration – you may port snippets (e.g., notarisation
  function) into your own pipelines, but start from the unified script
  first.

**Do NOT** run the legacy scripts on current source trees – they have
NOT been updated for macOS 15+/26.x SDKs and will likely fail.

----------------------------------------------------
4. Migration guide (TL;DR)
----------------------------------------------------
OLD COMMAND              ➜  NEW COMMAND
-------------------------    -----------------------------
./build_skyscope_oclp.sh     ./skyscope_unified_compiler.sh --build
./install_skyscope.sh        ./skyscope_unified_compiler.sh --install
./build_complete_skyscope.sh # Not needed – use --build / --install
(build_and_release handled   automatic GitHub Action + unified script)
by CI only)

----------------------------------------------------
5. Cleanup Policy
----------------------------------------------------
Legacy scripts are archived here to keep commit history slim. They will
be **removed in v2.0** once all users have migrated.  Feel free to open
issues if any functionality is missing from the new workflow.

----------------------------------------------------
End of file
====================================================
