LEVELS = {"quiet": 0, "normal": 1, "verbose": 2, "trace": 3}


class Logger:
    def __init__(self, level="normal"):
        self.level = self.validate(level)

    @staticmethod
    def validate(level):
        level = str(level).lower()
        if level not in LEVELS:
            raise ValueError(f"invalid verbosity level: {level}; expected quiet, normal, verbose, or trace")
        return level

    def set_level(self, level):
        self.level = self.validate(level)

    def __call__(self, message, level="normal"):
        if LEVELS[level] <= LEVELS[self.level]:
            print(message)
