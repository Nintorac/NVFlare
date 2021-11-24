import os

from torch.utils.tensorboard import SummaryWriter

from nvflare.apis.analytix import Data as AnalyticsData
from nvflare.apis.analytix import DataType as AnalyticsDataType
from nvflare.apis.dxo import from_shareable
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.app_common.widgets.streaming import AnalyticsReceiver

FUNCTION_MAPPING = {
    AnalyticsDataType.SCALAR: "add_scalar",
    AnalyticsDataType.TEXT: "add_text",
    AnalyticsDataType.IMAGE: "add_image",
    AnalyticsDataType.SCALARS: "add_scalars",
}


class TBAnalyticsReceiver(AnalyticsReceiver):
    """
    Folder structure:

    #  inside run_XX folder
    # - workspace
    #    - run_01 (already created):
    #        - output_dir (default: tb_events):
    #           - peer_name_1:
    #           - peer_name_2:
    #
    #    - run_02 (already created):
    #        - output_dir (default: tb_events):
    #           - peer_name_1:
    #           - peer_name_2:
    #
    """

    def __init__(self, tb_folder="tb_events", events=None):
        super().__init__(events=events)
        self.writer = {}
        self.tb_folder = tb_folder
        self.root_log_dir = None

    def initialize(self, fl_ctx: FLContext):
        workspace = fl_ctx.get_engine().get_workspace()
        run_dir = workspace.get_run_dir(fl_ctx.get_run_number())
        root_log_dir = os.path.join(run_dir, self.tb_folder)
        os.makedirs(root_log_dir, exist_ok=True)
        self.root_log_dir = root_log_dir

    def save(self, fl_ctx: FLContext, shareable: Shareable, record_origin):
        dxo = from_shareable(shareable)
        analytic_data = AnalyticsData.from_dxo(dxo)

        writer = self.writer.get(record_origin)
        if writer is None:
            peer_log_dir = os.path.join(self.root_log_dir, record_origin)
            writer = SummaryWriter(log_dir=peer_log_dir)
            self.writer[record_origin] = writer

        # depend on the type in dxo do different things
        for k, v in dxo.data.items():
            tag_name = f"{k}"
            self.log_debug(
                fl_ctx,
                f"save tag {tag_name} and value {v} with type {analytic_data.data_type} from {record_origin}",
                fire_event=False,
            )
            func_name = FUNCTION_MAPPING.get(analytic_data.data_type, None)
            if func_name is None:
                self.log_error(fl_ctx, f"The data_type {analytic_data.data_type} is not supported.", fire_event=False)
                continue

            func = getattr(writer, func_name)
            if isinstance(analytic_data.kwargs, dict):
                func(tag_name, v, **analytic_data.kwargs)
            else:
                func(tag_name, v)

    def finalize(self, fl_ctx: FLContext):
        for writer in self.writer.values():
            writer.flush()
            writer.close()