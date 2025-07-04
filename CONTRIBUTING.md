# Contributing to this Repository

## Organization

Please reference the [README.md][readme-uri] for the file layout of this repository.

### Plugin Batch Files

The plugin folder contains the following batch files in a `.build` subfolder to make development less painful. The batch files should be run from within that folder.

| Batch file  | Purpose                                                                                                         |
|-------------|-----------------------------------------------------------------------------------------------------------------|
| `build.cmd` | Compile the translations into .mo files, copy common files, construct the plugin zip, install in calibre.       |
| `debug.cmd` | Same as `build.cmd` with the addition of launching calibre in debug mode. Also useful for testing translations. |

Mostly you will be using `debug.cmd`. This allows you to see any errors when calibre attempts to load the plugin zip (e.g. in the VS Code console window), and then interactively test the plugin. Close calibre manually when you are finished testing.

### Environment Variables

- The calibre environment variables are documented [here](https://manual.calibre-ebook.com/customize.html)
- The following are useful to know/in addition:

| Environment Variable       | Purpose                                                                                                                                                                    |
|----------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `CALIBRE_CONFIG_DIRECTORY` | If using calibre portable, set this to the location of the `Calibre Settings` subfolder.<br>Otherwise calibre-customize in `build.cmd` will insert into your main calibre. |
| `CALIBRE_DIRECTORY`        | Custom variable I added support for, used by `build.cmd`<br>Set to folder location of your `calibre-debug.exe`.<br>Only necessary if calibre is not in your path.          |


---
## Working with Visual Studio Code

You can use any text editor you like to modify these plugins - it really doesn't matter and depends on how much intellisense support you are after and what you feel most productive with. If you did use something else though please make sure that any local workspace files that editor creates are excluded in the `.gitignore` to keep the noise away from others.

If however you are wanting to attach a debugger to a running calibre process for full stepping through code etc that is not what VS Code does. Your debugging is going to be limited to `print()` and `log` statements. If you think you need more interactive debugging then this thread may offer some tips:
[A free Calibre Windows development environment using Visual Studio](https://www.mobileread.com/forums/showthread.php?t=251201)

### Navigating calibre code from VS Code

Entirely optional but you might find it useful to have the calibre source code easily accessible in addition to this plugins repo. Particularly when you need to understand the calibre API or look to see how it should be used.

To start you should clone the [calibre source code](https://github.com/kovidgoyal/calibre.git) repository to your machine to a `calibre` folder.

### Option A: To search calibre source code and this code repo together in VS Code explorer
- After cloning, move this repo `calibre_plugins` folder to sit within the `calibre\src` repo subfolder above. 
- Your local folder should look like this:
```
calibre
  ...
  src
    calibre
    calibre_plugins
    ...
```
- Open the `calbre\src` folder as your workspace folder in VS Code. That will include both the `calibre` and `calibre_plugin` subfolders
- This approach can be handy if you want are doing a lot of searching of calibre code for how to use a function etc.

### Option B: To focus on just these plugins, with ctrl+click navigation to calibre source

- Create a `.env` file in the root of your workspace (e.g. in this repo folder root where this README is located)
- Set the contents to be the following, with the full path to your `calibre\src` folder:
```
PYTHONPATH=<path_to_calibre_src>
```
- Create/modify your `.vscode\settings.json` to point to this file with at least this: 
```
{
    "python.envFile": "${workspaceFolder}/.env"
}
```
- Now when browsing plugin code, all linting warnings for calibre python functions should be resolved. 
- You can ctrl+click to navigate into calibre source code, yay!.
- This option is useful if you are focused on some quick plugin changes and want a more lightweight VS Code workspace.

You can of course do both of the above or mixing and matching - for instance the same approach for using a `.env` file could be used if you wanted to open just one plugin subfolder within this repo in VS Code. See [Using Python environments in VS Code](https://code.visualstudio.com/docs/python/environments)

### Virtual Environments

The above approach will allow resolving calibre imports but not third party libraries such as PyQt5, six or lxml. If you want intellisense for those, then you need a few more steps to create a virtual Python environment in VS Code.

1. From the powershell prompt in VS Code with the workspace loaded, run:
    ```
    py -3 -m venv .venv
    .venv\scripts\activate
    ```
2. Now you can try to install third party packages you see a plugin requires, e.g.
    ```
    python -m pip install PyQt5
    python -m pip install six
    python -m pip install lxml
    ...
    ```
For more information, see: [Getting Started with Python in VS Code](https://code.visualstudio.com/docs/python/python-tutorial)

[readme-uri]: README.md
