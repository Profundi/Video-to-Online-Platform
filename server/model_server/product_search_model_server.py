import json
import os
import time
from concurrent import futures

# rpc imports
import grpc

from hysia.search.product_search import ProductSearch
from hysia.utils.logger import Logger
from hysia.utils.perf import StreamSuppressor
from model_server import device_config
from model_server.misc import obtain_device
from protos import api2msl_pb2, api2msl_pb2_grpc

# Time constant
_ONE_DAY_IN_SECONDS = 24 * 60 * 60

VIDEO_DATA_PATH = '/data/disk2/hysia_data/Stanford_Online_Products/'

logger = Logger(
    name='product_search_model_server',
    severity_levels={'StreamHandler': 'INFO'}
)


def load_search_machine():
    with StreamSuppressor():
        search_machine = ProductSearch(VIDEO_DATA_PATH)
    return search_machine


# Custom request servicer
class Api2MslServicer(api2msl_pb2_grpc.Api2MslServicer):
    def __init__(self):
        super().__init__()
        cuda, device_num = obtain_device(device_config.product_search_server)

        if cuda:
            os.environ['CUDA_VISIBLE_DEVICES'] = str(device_num)
        else:
            os.environ['CUDA_VISIBLE_DEVICES'] = ''

        logger.info(f'Using {"CUDA:" if cuda else "CPU"}{os.environ["CUDA_VISIBLE_DEVICES"]}')
        self.search_machine = load_search_machine()

    def GetJson(self, request, context):
        time_stamp = int(request.buf.decode())
        video_path = request.meta
        logger.info('Searching at ' + str(time_stamp) + ' in ' + video_path)
        # Decode image from buf
        with StreamSuppressor():
            results = self.search_machine.search(time_stamp, video_path)
        logger.info('Found ' + str(len(results)) + ' similar products')
        # Convert tensor to list to make it serializable
        for res in results:

            # TODO Here has some bugs
            if not type(res['FEATURE']) == list:
                res['FEATURE'] = res['FEATURE'].tolist()
        return api2msl_pb2.JsonReply(json=json.dumps(results), meta='')


def main():
    # gRPC server configurations
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    api2msl_pb2_grpc.add_Api2MslServicer_to_server(Api2MslServicer(), server)
    server.add_insecure_port('[::]:50054')
    server.start()
    logger.info('Listening on port 50054')
    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        logger.info('Shutting down product search model server')
        server.stop(0)


if __name__ == '__main__':
    main()
