# main.py
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
