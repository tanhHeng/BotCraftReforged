from botcraft.runtime_args import RuntimeArgs


def run_botcraft(args: RuntimeArgs) -> None:
    """Run the standalone QQ runtime with the selected deployment arguments.
    
    :param args: Deployment action and selected configuration and permission paths.
    :return: No return value.
    """
    from botcraft.runtime import Runtime
    Runtime(args).run()
