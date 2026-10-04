from botcraft.runtime_args import RuntimeArgs


def run_botcraft(args: RuntimeArgs) -> None:
    from botcraft.runtime import Runtime
    Runtime(args).run()
